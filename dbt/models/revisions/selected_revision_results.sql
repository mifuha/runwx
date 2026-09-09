{{ config(enabled=var('enable_revision_preview', false)) }}

with revisions as (
    select * from {{ source('revision_preview', 'analysis_revisions') }}
    qualify count(*) over (partition by revision_id) = 1
), selections as (
    select * from {{ source('revision_preview', 'event_selections') }}
    qualify count(*) over (partition by event_id) = 1
), attempts as (
    select * from {{ source('revision_preview', 'revision_attempts') }}
    qualify count(*) over (partition by attempt_id) = 1
), candidates as (
    select * from {{ source('revision_preview', 'revision_result_rows') }}
), complete_candidates as (
    -- Check the whole revision before exposing any of its candidate rows.
    select c.revision_id
    from candidates c
    join revisions r on c.revision_id = r.revision_id
    where r.snapshot_scope = 'complete'
    group by c.revision_id
    having count(*) = max(r.candidate_count)
        and count(distinct c.source_row_number) = count(*)
        and min(c.source_row_number) = 1 and max(c.source_row_number) = count(*)
        and countif(c.validation_status = 'accepted') = max(r.accepted_count)
        and countif(c.validation_status = 'skipped') = max(r.skipped_count)
        and countif(c.validation_status = 'invalid') = max(r.invalid_count)
        and countif(c.validation_status in ('accepted', 'skipped', 'invalid')) = count(*)
        and countif(c.weather_match_status = 'matched') = max(r.weather_matched_count)
        and countif(
            c.event_id is distinct from r.event_id
            or c.race_sha256 is distinct from r.race_sha256
            or c.weather_sha256 is distinct from r.weather_sha256
            or c.race_kind is distinct from r.race_kind
            or c.source_row_id is distinct from concat(
                r.event_id, ':', r.race_sha256, ':', cast(c.source_row_number as string)
            )
        ) = 0
)
select c.*, r.settings_json as revision_settings_json, r.code_sha256
from candidates c
join complete_candidates valid on c.revision_id = valid.revision_id
join revisions r on c.revision_id = r.revision_id
join selections s on s.event_id = r.event_id and s.revision_id = r.revision_id
-- EXISTS checks a receipt without adding one result row per execution attempt.
where exists (
    select 1 from attempts a
    where a.attempt_id = s.successful_attempt_id
        and a.revision_id = r.revision_id
        and a.status = 'succeeded'
        and a.validation_scope = 'warehouse'
        and regexp_contains(a.validation_code_sha256, r'^[0-9a-f]{64}$')
        and nullif(trim(a.validation_invocation_id), '') is not null
)
