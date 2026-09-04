# Project Briefing

## What This Project Is

`runwx` is a small Python project for analyzing how weather relates to race performance.

It does this by converting race results into generic `Run` records, enriching them with nearby weather observations, summarizing both performance and weather, and comparing events over time.

A key rule of the current race-analysis design is:

> Multi-event comparison is only valid when events share the same canonical `course_id`.  
> Same distance alone is not sufficient.

The current architecture is layered:

- `runwx.domain`: core types and pure business logic
- `runwx.services`: orchestration and use-case flows
- `runwx.adapters`: external I/O boundaries such as JSON, CSV, SQLite, and Open-Meteo

The canonical code paths should prefer these layered modules directly.

## Current Status

- the end-to-end race-analysis vertical slice works
- demo scripts exist for both single-event and multi-event analysis
- the full test suite is passing
- the current workflow is stable for sample/demo data
- the architecture is modular and ready for the next layer of real-world ingestion work

Useful commands:

```bash
python scripts/demo_race_analysis.py
python scripts/demo_race_comparison.py
pytest
