-- Legacy mode requires one export; selected mode permits zero or more events,
-- each with exactly one complete context. DISTINCT retains nullable settings.
with contexts as (
    select distinct {{ context_columns() }}
    from {{ ref('stg_race_results') }}
)
{% if var('enable_revision_preview', false) %}
select event_id, count(*) as context_count
from contexts
group by event_id
having count(*) != 1
    or countif(event_id is null or revision_id is null or code_sha256 is null
        or top_n_requested is null or top_n_requested <= 0) > 0
{% else %}
select count(*) as context_count
from contexts
having count(*) != 1
{% endif %}
