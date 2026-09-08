{{ config(enabled=var('enable_revision_preview', false)) }}

-- A bad pointer must be visible as a test failure, even if the model emits no rows.
with selected as (
    select event_id, count(*) as pointer_count, min(revision_id) as revision_id
    from {{ source('revision_preview', 'event_selections') }}
    group by event_id
), metadata as (
    select revision_id, count(*) as metadata_count, max(candidate_count) as candidate_count
    from {{ source('revision_preview', 'analysis_revisions') }}
    group by revision_id
), actual as (
    select event_id, revision_id, count(*) as candidate_count,
        count(distinct source_row_number) as unique_row_count
    from {{ ref('selected_revision_results') }}
    group by event_id, revision_id
)
select s.event_id
from selected s
left join metadata m on s.revision_id = m.revision_id
left join actual a on s.event_id = a.event_id and s.revision_id = a.revision_id
where s.pointer_count != 1 or coalesce(m.metadata_count, 0) != 1
    or coalesce(a.candidate_count, 0) != m.candidate_count
    or coalesce(m.candidate_count, 0) <= 0
    or a.unique_row_count != a.candidate_count
