{{ config(enabled=var('gnr_sample_tables', []) | length > 0, tags=['gnr']) }}
{% if var('gnr_sample_tables', []) | length > 0 %}
with expected as (
    {% for table in gnr_sample_tables() %}
        {% if not loop.first %} union all {% endif %}
        select '{{ table }}' as snapshot_table
    {% endfor %}
), actual as (
    select * from {{ ref('mart_gnr_edition_summary') }}
)
select coalesce(e.snapshot_table, a.snapshot_table) as failing_table
from expected as e
full outer join actual as a using (snapshot_table)
where e.snapshot_table is null or a.snapshot_table is null
    or a.sample_size != 1000 or a.declared_sample_size != 1000
    or a.distinct_source_rows != 1000 or a.distinct_sample_ranks != 1000
    or a.min_sample_rank != 1 or a.max_sample_rank != 1000
    or a.distinct_contexts != 1
    or a.chip_count + a.gun_count + a.unknown_count != 1000
    or a.course_id != 'great-north-run-traditional' or a.distance_m != 21100
    or a.export_schema != 'gnr_sample_v1'
    or a.distance_basis != 'provider distanceInKm'
    or a.race_kind != 'historical' or a.weather_kind != 'historical_reanalysis'
    or a.sample_label != 'Top 1,000 only*' or a.source_count != 2000
    or a.weather_context_basis != 'fixed_event_window'
    or a.weather_start_local != '10:00' or a.weather_end_local != '14:00'
    or a.event_id not like 'greatrun:%'
    or not regexp_contains(a.race_sha256, r'^[0-9a-f]{64}$')
    or not regexp_contains(a.weather_sha256, r'^[0-9a-f]{64}$')
    or not regexp_contains(a.weather_request_sha256, r'^[0-9a-f]{64}$')
    or cast(extract(year from a.race_date) as string)
        != regexp_extract(a.snapshot_table, r'gnr_([0-9]{4})_')
    or a.best_duration_s <= 0
    or a.duration_p25_s > a.median_duration_s
    or a.median_duration_s > a.duration_p75_s
{% endif %}
