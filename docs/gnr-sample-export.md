# Great North Run sample export

`export-gnr-sample` prepares the agreed **Top 1,000 only*** comparison from saved
Great Run leaderboard and category responses. It runs offline and emits NDJSON.
It supports the 19 qualified traditional-course editions: 2006–2019 and 2022–2026.
The changed 2021 course is excluded. This is a course-family grouping, not proof
that every minor diversion was identical.

\*Fastest 1,000 running results from the available mass-participation leaderboard,
ranked by published finish time. Statistics describe this group, not all finishers
or the separate elite race.

## Inputs and command

Keep the original leaderboard JSON, category JSON, ERA5 JSON and weather capture
record. Supply the three expected source hashes from the reviewed capture records.
The weather record contains `provider`, `dataset`, `params`, `url`, `status`,
`sha256` and `bytes`. Its settings must identify the race date, ERA5, UTC, Celsius,
m/s, mm and the Newcastle start-area point at 54.984, -1.620.

```bash
python -m runwx export-gnr-sample \
  --race-json saved/2019-results.json \
  --categories-json saved/2019-categories.json \
  --weather-json saved/2019-era5.json \
  --weather-request saved/2019-weather-request.json \
  --race-id 881 --race-date 2019-09-08 \
  --race-sha256 "$RACE_SHA256" \
  --categories-sha256 "$CATEGORIES_SHA256" \
  --weather-sha256 "$WEATHER_SHA256"
```

The whole export is validated and serialized before anything is printed. Save
successful output to a new file; shell redirection can truncate an existing file
before Python starts. Identical inputs give identical bytes. Corrected input bytes
have different hashes; a corrected race snapshot also has different source row IDs.

## Selection and timing

The exporter combines the saved lists of 1,000 men and 1,000 women, then selects
1,000 running results overall. It excludes explicit wheelchair flags and named
wheelchair, handcycle and elite categories. It does not infer categories from pace.
Published finish time orders the sample; the provider result ID breaks ties.
Both source-list tails must be strictly slower than the selected cutoff. Otherwise
the unseen results could change the sample and the export fails.

Every row retains its source locator, sample rank, duration and `chip`, `gun` or
`unknown` timing basis. Missing timing labels stay unknown. No names, dates of birth,
bibs or athlete IDs enter the export. A sample rank is not an official race place.

## Weather context

The exporter reuses the existing weather validation and translation functions.
It requires all 24 hourly UTC observations on the race date. Each row carries the
same labelled `weather_context`: hourly medians at 10:00–14:00 Europe/London for
temperature, wind and humidity. Rain is the sum of preceding-hour amounts ending
at 11:00–14:00, covering the four-hour window. UTC offsets follow the local timezone.

This is a fixed window at an approximate start-area location. ERA5 is reanalysis,
not an observation beside each runner or along the whole course. Individual starts
are unknown, so the export does not claim a runner midpoint weather match.
Mixed timing and changing participant fields also limit year-to-year comparisons.

## Current boundary

The explicit `gnr_sample_v1` contract includes sample scope/counts, cutoff ties,
timing basis, source hashes, weather-request hash and window/location settings.
It reuses the deterministic NDJSON encoder. The existing full-field export and
Cloud Run commands remain supported as before.

This step prepares files only. The [sample-aware BigQuery loader](gnr-sample-load.md)
checks this contract separately; the full-result loader still rejects it. dbt
models and public presentation need their own integration work. No cloud load or
public GNR comparison is claimed by this command.
