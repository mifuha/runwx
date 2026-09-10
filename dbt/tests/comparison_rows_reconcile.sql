{{ config(enabled=var('comparison_datasets', []) | length > 0, tags=['comparison']) }}
{% set datasets = comparison_datasets() %}
{% if datasets %}
-- Scalar counts detect an absent baseline or silently lost edition.
select 'missing_or_repeated_edition' as failure
from (select count(*) as edition_count from {{ ref('mart_course_comparison') }})
where edition_count != {{ datasets | length }}
{% endif %}
