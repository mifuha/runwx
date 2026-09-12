"""Cloud Run entrypoint: environment configuration and keyless Storage client."""

from datetime import timedelta
import json
import os

from runwx.adapters.gcs.report_io import run_stored_report


def main(*, client=None):
    settings = json.loads(os.environ["RUNWX_REPORT_SETTINGS"])
    settings["max_gap"] = timedelta(minutes=settings.pop("max_gap_minutes", 30))
    execution = {
        "job": os.environ["CLOUD_RUN_JOB"],
        "name": os.environ["CLOUD_RUN_EXECUTION"],
        "task_index": int(os.environ["CLOUD_RUN_TASK_INDEX"]),
        "task_attempt": int(os.environ["CLOUD_RUN_TASK_ATTEMPT"]),
        "image": os.environ["RUNWX_IMAGE"],
        "source_revision": os.environ["RUNWX_SOURCE_REVISION"],
    }
    if client is None:
        from google.cloud import storage

        # Cloud Run supplies credentials for the job's service account; no key file.
        client = storage.Client()
    outputs = run_stored_report(
        client,
        race_uri=os.environ["RUNWX_RACE_URI"],
        race_sha256=os.environ["RUNWX_RACE_SHA256"],
        weather_uri=os.environ["RUNWX_WEATHER_URI"],
        weather_sha256=os.environ["RUNWX_WEATHER_SHA256"],
        output_prefix=os.environ["RUNWX_OUTPUT_PREFIX"],
        execution=execution, settings=settings,
    )
    print(json.dumps({**outputs, "execution": execution}, sort_keys=True))


if __name__ == "__main__":
    main()
