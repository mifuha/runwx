with quality as (
    select
        count(*) as candidates,
        countif(validation_status = 'accepted') as accepted,
        countif(validation_status = 'skipped') as skipped,
        countif(validation_status = 'invalid') as invalid
    from {{ ref('stg_race_results') }}
), facts as (
    select
        count(*) as finishers,
        countif(weather_match_status = 'matched') as matched,
        countif(weather_match_status = 'unmatched') as unmatched
    from {{ ref('fct_race_results') }}
), mart_count as (
    -- This scalar count catches an empty mart; a query over mart rows cannot.
    select count(*) as summaries from {{ ref('mart_event_summary') }}
)
select 'summary_count' as failure
from mart_count
where summaries != 1
union all
select 'counts_coverage_or_settings' as failure
from {{ ref('mart_event_summary') }} as mart
cross join quality
cross join facts
where mart.candidate_count is distinct from quality.candidates
    or mart.accepted_count is distinct from quality.accepted
    or mart.skipped_count is distinct from quality.skipped
    or mart.invalid_count is distinct from quality.invalid
    or quality.candidates != quality.accepted + quality.skipped + quality.invalid
    or mart.finisher_count is distinct from facts.finishers
    or facts.finishers != quality.accepted
    or mart.weather_matched_count is distinct from facts.matched
    or mart.weather_unmatched_count is distinct from facts.unmatched
    or facts.matched + facts.unmatched != quality.accepted
    or mart.weather_coverage_fraction is distinct from safe_divide(facts.matched, facts.finishers)
    or mart.weather_coverage_status is distinct from case
        when facts.finishers = 0 then 'not_applicable'
        when facts.matched = 0 then 'unavailable'
        when facts.matched = facts.finishers then 'complete'
        else 'partial'
    end
    or mart.top_n_requested is distinct from {{ var('top_n', 20) }}
    or mart.top_n_effective is distinct from least({{ var('top_n', 20) }}, facts.finishers)
    or mart.duration_unit is distinct from 'seconds'
    or mart.pace_unit is distinct from 'seconds_per_kilometre'
    or (
        facts.finishers = 0
        and (
            mart.best_duration_s is not null or mart.mean_duration_s is not null
            or mart.median_duration_s is not null or mart.top_n_median_duration_s is not null
            or mart.median_pace_s_per_km is not null or mart.top_n_median_pace_s_per_km is not null
        )
    )
    or (
        facts.finishers > 0
        and (
            mart.best_duration_s is null or mart.mean_duration_s is null
            or mart.median_duration_s is null or mart.top_n_median_duration_s is null
            or mart.median_pace_s_per_km is null or mart.top_n_median_pace_s_per_km is null
        )
    )
