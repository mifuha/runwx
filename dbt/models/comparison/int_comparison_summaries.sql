{{ config(materialized='ephemeral') }}
-- Existing, separately built edition views; this model does not rebuild them.
{{ comparison_union('mart_event_summary') }}
