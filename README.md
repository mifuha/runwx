# runwx

A small Python data pipeline that aligns running activities with weather observations and produces a clean, typed `RunWithWeather` record for downstream analysis.

I built this project to combine two interests: running and clean data processing.  
The goal is to practice a real pipeline mindset (validation, alignment, enrichment, testing) on a domain I actually care about.

The project is built in small, testable steps:
- validated domain models (`Run`, `WeatherObs`)
- time alignment logic (nearest weather by run midpoint)
- enrichment stage (`RunWithWeather`)
- pipeline orchestration (`align -> enrich -> skip`)
- pytest coverage across core modules

---

## Why this project exists

Real-world data work is rarely just analysis.

Most of the work is usually:
1. ingesting data from different sources
2. validating and normalizing it
3. joining/aligning it (often by time)
4. storing it in a reusable format
5. then analyzing/modeling it

`runwx` is a small, interview-friendly project that shows that pipeline mindset in Python.

---

## What it does today

### Domain models (validated + immutable)
- `Run(started_at, duration_s, distance_m)`
- `WeatherObs(observed_at, temp_c, wind_mps, precipitation_mm)`
- `RunWithWeather(run, weather)`

Validation rules:
- timestamps must be timezone-aware
- `duration_s > 0`
- `distance_m > 0`
- `wind_mps >= 0`
- `precipitation_mm >= 0`

Dataclasses are `frozen=True` to keep core data immutable.

### Alignment (time-based)
For each run:
- compute the run anchor time as the **midpoint**
- find the nearest weather observation in time
- reject if the closest observation is farther than `max_gap` (default: 30 minutes)

### Enrichment
If a valid match exists, combine the run + weather into:
- `RunWithWeather`

### Pipeline orchestration
The pipeline:
- loops through runs
- aligns weather
- enriches valid matches
- records skipped runs (with a reason)

---

## Project structure (current)

```text
.
├── pyproject.toml
├── setup.cfg
├── README.md
├── src/
│   └── runwx/
│       ├── __init__.py
│       ├── __main__.py
│       ├── models.py
│       ├── align.py
│       ├── enrich.py
│       ├── pipeline.py
│       ├── main.py
│       └── utils.py
└── tests/
    ├── test_models.py
    ├── test_align.py
    ├── test_enrich.py
    ├── test_pipeline.py
    ├── test_main.py
    └── test_utils.py