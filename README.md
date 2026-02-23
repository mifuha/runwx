# runwx

A small Python data pipeline that aligns running activities with weather observations and produces a clean, typed `RunWithWeather` record for downstream analysis.

I built this project to combine two interests: running and clean data processing.  
The goal is to practice a real pipeline mindset (validation, alignment, enrichment, testing) on a domain I actually care about.

---

## What the project does

- defines validated, immutable domain models (`Run`, `WeatherObs`)
- matches runs to the nearest weather observation in time
- enriches runs with weather context
- provides a small orchestration pipeline
- supports CSV ingestion for runs and weather
- includes pytest coverage across core modules

---

## Why this project exists

Real-world data work is rarely just analysis.

Most of the work usually involves:

1. ingesting data from different sources  
2. validating and normalizing it  
3. joining or aligning it (often by time)  
4. storing it in a reusable format  
5. then analyzing or modeling it  

`runwx` is a small project that demonstrates that pipeline mindset in Python.

---

## Core concepts

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

---

### Alignment (time-based)

For each run:

- compute the run anchor time as the **midpoint**  
- find the nearest weather observation in time  
- reject if the closest observation is farther than `max_gap` (default: 30 minutes)  

---

### Pipeline orchestration

The pipeline:

- loops through runs  
- aligns weather  
- enriches valid matches  
- records skipped runs (with a reason)  

---

### CSV ingestion

The project can load:

- runs from `runs.csv`  
- weather observations from `weather.csv`  

CSV rows are parsed and converted into typed domain objects before entering the pipeline.

---

## Requirements

- Python 3.10+ (tested locally on Python 3.13)  
- Git  

---

## Setup (Git Bash on Windows)

From the project root:

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -U pip
pip install -e .
pip install pytest