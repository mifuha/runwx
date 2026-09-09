{% set selected = var('enable_revision_preview', false) %}
{% set top_n = 'top_n_requested' if selected else var('top_n', 20) %}
{% if not selected and (top_n is not integer or top_n <= 0) %}
    {{ exceptions.raise_compiler_error('top_n must be a positive integer') }}
{% endif %}

with context as (
    select distinct {{ context_columns() }}
    from {{ ref('stg_race_results') }}
), quality as (
    select
        {{ analysis_keys() }},
        count(*) as candidate_count,
        countif(validation_status = 'accepted') as accepted_count,
        countif(validation_status = 'skipped') as skipped_count,
        countif(validation_status = 'invalid') as invalid_count
    from {{ ref('stg_race_results') }}
    group by {{ analysis_keys() }}
), ranked as (
    select
        *,
        row_number() over (
            partition by {{ analysis_keys() }} order by duration_s, source_row_number
        ) as finish_rank
    from {{ ref('fct_race_results') }}
), medians as (
    select
        *,
        percentile_cont(cast(duration_s as float64), 0.5)
            over (partition by {{ analysis_keys() }}) as median_duration_s,
        percentile_cont(
            if(finish_rank <= {{ top_n }}, cast(duration_s as float64), null), 0.5
        ) over (partition by {{ analysis_keys() }}) as top_n_median_duration_s
    from ranked
), summary as (
    select
        {{ analysis_keys() }},
        count(*) as finisher_count,
        min(duration_s) as best_duration_s,
        avg(duration_s) as mean_duration_s,
        max(median_duration_s) as median_duration_s,
        max(top_n_median_duration_s) as top_n_median_duration_s,
        countif(weather_match_status = 'matched') as weather_matched_count
    from medians
    group by {{ analysis_keys() }}
), totals as (
    select
        context.*,
        quality.* except ({{ analysis_keys() }}),
        coalesce(summary.finisher_count, 0) as finisher_count,
        summary.best_duration_s,
        summary.mean_duration_s,
        summary.median_duration_s,
        summary.top_n_median_duration_s,
        coalesce(summary.weather_matched_count, 0) as weather_matched_count
    from context
    join quality using ({{ analysis_keys() }})
    -- Keep quality counts for an all-rejected event; its performance stays NULL.
    left join summary using ({{ analysis_keys() }})
    {% if selected %}
    where context.top_n_requested > 0
        and (select count(*) from context as other where other.event_id = context.event_id) = 1
    {% else %}
    -- Preserve the original demo's one-export constraint.
    where (select count(*) from context) = 1
    {% endif %}
)
select
    *,
    median_duration_s / (distance_m / 1000.0) as median_pace_s_per_km,
    top_n_median_duration_s / (distance_m / 1000.0) as top_n_median_pace_s_per_km,
    {% if not selected %}{{ top_n }} as top_n_requested,{% endif %}
    least({{ top_n }}, finisher_count) as top_n_effective,
    finisher_count - weather_matched_count as weather_unmatched_count,
    safe_divide(weather_matched_count, finisher_count) as weather_coverage_fraction,
    case
        when finisher_count = 0 then 'not_applicable'
        when weather_matched_count = 0 then 'unavailable'
        when weather_matched_count = finisher_count then 'complete'
        else 'partial'
    end as weather_coverage_status,
    'seconds' as duration_unit,
    'seconds_per_kilometre' as pace_unit
from totals
