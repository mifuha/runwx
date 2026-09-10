-- A source table holds one complete export. NULL is part of its context,
-- so DISTINCT tuples distinguish unknown timing from a stated timing basis.
with contexts as (
    select distinct {{ context_columns() }}
    from {{ ref('stg_race_results') }}
)
select count(*) as context_count
from contexts
having count(*) != 1
