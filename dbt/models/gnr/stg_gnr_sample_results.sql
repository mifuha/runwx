{{ config(materialized='ephemeral') }}
-- Only the explicitly supplied, hash-derived GNR sample snapshots are read.
{{ gnr_sample_union() }}
