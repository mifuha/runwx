{{ config(enabled=var('comparison_datasets', []) | length > 0, tags=['comparison']) }}
{% set datasets = comparison_datasets() %}
{% if datasets %}
with expected as (
    {% for dataset in datasets %}
    {% if not loop.first %} union all {% endif %}
    select '{{ dataset }}' as snapshot_dataset
    {% endfor %}
), summaries as (
    select * from {{ ref('int_comparison_summaries') }}
), facts as (
    select snapshot_dataset, count(*) as finishers,
        count(distinct source_row_id) as distinct_finishers,
        countif(weather_match_status = 'matched') as matched
    from {{ ref('int_comparison_results') }}
    group by snapshot_dataset
), summary_counts as (
    select snapshot_dataset, count(*) as summaries from summaries group by snapshot_dataset
)
select e.snapshot_dataset
from expected as e
left join summary_counts as c using (snapshot_dataset)
left join summaries as s using (snapshot_dataset)
left join facts as f using (snapshot_dataset)
where coalesce(c.summaries, 0) != 1
    or s.finisher_count is distinct from coalesce(f.finishers, 0)
    or s.accepted_count is distinct from coalesce(f.finishers, 0)
    or coalesce(f.finishers, 0) != coalesce(f.distinct_finishers, 0)
    or s.weather_matched_count is distinct from coalesce(f.matched, 0)
    or s.weather_coverage_fraction is distinct from safe_divide(f.matched, f.finishers)
union all
select f.snapshot_dataset
from {{ ref('int_comparison_results') }} as f
join summaries as s using (snapshot_dataset)
where
    {% for field in ['export_schema_version', 'event_id', 'source', 'source_event_id',
                     'course_id', 'started_at_utc', 'distance_m', 'race_sha256',
                     'weather_sha256', 'race_kind', 'weather_kind', 'course_id_input',
                     'timezone_name', 'max_gap_seconds', 'alignment', 'tie_break',
                     'duration_precision', 'timing_basis'] %}
    {% if not loop.first %} or {% endif %}f.{{ field }} is distinct from s.{{ field }}
    {% endfor %}
{% endif %}
