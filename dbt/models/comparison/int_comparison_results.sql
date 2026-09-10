{{ config(materialized='ephemeral') }}
{{ comparison_union('fct_race_results') }}
