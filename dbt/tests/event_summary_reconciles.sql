{% set selected = var('enable_revision_preview', false) %}
with quality as (
    select
        {{ analysis_keys() }},
        {% if selected %}min(top_n_requested){% else %}{{ var('top_n', 20) }}{% endif %} as requested_n,
        count(*) as candidates,
        countif(validation_status = 'accepted') as accepted,
        countif(validation_status = 'skipped') as skipped,
        countif(validation_status = 'invalid') as invalid
    from {{ ref('stg_race_results') }}
    group by {{ analysis_keys() }}
), facts as (
    select
        {{ analysis_keys() }},
        count(*) as finishers,
        countif(weather_match_status = 'matched') as matched,
        countif(weather_match_status = 'unmatched') as unmatched
    from {{ ref('fct_race_results') }}
    group by {{ analysis_keys() }}
), expected as (
    select quality.*,
        coalesce(facts.finishers, 0) as finishers,
        coalesce(facts.matched, 0) as matched,
        coalesce(facts.unmatched, 0) as unmatched
    from quality left join facts using ({{ analysis_keys() }})
), mart_count as (
    select {{ analysis_keys() }}, count(*) as summaries from {{ ref('mart_event_summary') }}
    group by {{ analysis_keys() }}
), context_differences as (
    (select distinct {{ context_columns() }} from {{ ref('stg_race_results') }}
     except distinct
     select {{ context_columns() }} from {{ ref('mart_event_summary') }})
    union all
    (select {{ context_columns() }} from {{ ref('mart_event_summary') }}
     except distinct
     select distinct {{ context_columns() }} from {{ ref('stg_race_results') }})
)
select 'summary_count' as failure
from mart_count
where summaries != 1
union all
select 'summary_context' as failure from context_differences
union all
select 'counts_coverage_or_settings' as failure
from {{ ref('mart_event_summary') }} as mart
full outer join expected using ({{ analysis_keys() }})
-- A missing or extra summary must fail even if there are no mart rows to scan.
where mart.event_id is null or expected.event_id is null
    or mart.candidate_count is distinct from expected.candidates
    or mart.accepted_count is distinct from expected.accepted
    or mart.skipped_count is distinct from expected.skipped
    or mart.invalid_count is distinct from expected.invalid
    or expected.candidates != expected.accepted + expected.skipped + expected.invalid
    or mart.finisher_count is distinct from expected.finishers
    or expected.finishers != expected.accepted
    or mart.weather_matched_count is distinct from expected.matched
    or mart.weather_unmatched_count is distinct from expected.unmatched
    or expected.matched + expected.unmatched != expected.accepted
    or mart.weather_coverage_fraction is distinct from safe_divide(expected.matched, expected.finishers)
    or mart.weather_coverage_status is distinct from case
        when expected.finishers = 0 then 'not_applicable'
        when expected.matched = 0 then 'unavailable'
        when expected.matched = expected.finishers then 'complete'
        else 'partial'
    end
    or mart.top_n_requested is distinct from expected.requested_n
    or mart.top_n_effective is distinct from least(expected.requested_n, expected.finishers)
    or mart.duration_unit is distinct from 'seconds'
    or mart.pace_unit is distinct from 'seconds_per_kilometre'
    or (
        expected.finishers = 0
        and (
            mart.best_duration_s is not null or mart.mean_duration_s is not null
            or mart.median_duration_s is not null or mart.top_n_median_duration_s is not null
            or mart.median_pace_s_per_km is not null or mart.top_n_median_pace_s_per_km is not null
        )
    )
    or (
        expected.finishers > 0
        and (
            mart.best_duration_s is null or mart.mean_duration_s is null
            or mart.median_duration_s is null or mart.top_n_median_duration_s is null
            or mart.median_pace_s_per_km is null or mart.top_n_median_pace_s_per_km is null
        )
    )
