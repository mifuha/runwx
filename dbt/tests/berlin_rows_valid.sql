{{ config(enabled=var('berlin_research_tables', []) | length > 0, tags=['berlin']) }}
{% if var('berlin_research_tables', []) | length > 0 %}
select snapshot_table, source_row_number
from {{ ref('stg_berlin_research_results') }}
where export_schema is distinct from 'berlin_research_v1'
    or dataset_version is distinct from 2
    or population_basis is distinct from 'published_research_capture'
    or course_basis is distinct from 'post_2003_course_era_not_identical_routes'
    or distance_m is distinct from 42195
    or place is not null or age is not null or timing_basis is not null
    or source_row_number is null or source_row_number <= 0
    or source_row_id is distinct from concat('berlin-kaggle-v2:', race_sha256, ':', cast(source_row_number as string))
    or cast(extract(year from race_date) as string) is distinct from regexp_extract(snapshot_table, r'berlin_([0-9]{4})_')
    or substr(preparation_report_sha256, 1, 12) is distinct from regexp_extract(snapshot_table, r'_research_([0-9a-f]{12})$')
    or validation_status is null or validation_status not in ('accepted', 'held')
    or (validation_status = 'accepted' and (duration_s is null or duration_s <= 0 or validation_reason is not null))
    or (validation_status = 'held' and (duration_s is not null or validation_reason is null))
    or weather_context.basis is distinct from 'fixed_edition_window'
    or weather_context.timezone is distinct from 'Europe/Berlin'
    or weather_context.start_local is distinct from '09:00'
    or weather_context.end_local is distinct from '15:00'
    or weather_context.observation_count is distinct from 7
    or datetime(weather_context.start_utc, 'Europe/Berlin') is distinct from datetime(race_date, time '09:00:00')
    or datetime(weather_context.end_utc, 'Europe/Berlin') is distinct from datetime(race_date, time '15:00:00')
{% endif %}
