"""Airflow passes references; shared batch and dbt functions perform the work."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from runwx.services.gnr_batch import BatchConfig, execute_batch, prepare_batch
from runwx.services.gnr_sample_export import _json


class RunPaths(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    config: str
    output: str
    dbt_project: str
    dbt_python: str


def prepare(value):
    paths = RunPaths.model_validate(value)
    for name in ('config', 'output', 'dbt_project', 'dbt_python'):
        if not Path(getattr(paths, name)).is_absolute():
            raise ValueError('Airflow requires absolute paths shared by its workers')
    if (not (Path(paths.dbt_project) / 'dbt_project.yml').is_file()
            or not Path(paths.dbt_python).is_file()):
        raise ValueError('dbt project and Python executable must exist on the worker')
    config = BatchConfig.model_validate(_json(Path(paths.config).read_bytes()))
    if config.analytics is None:
        raise ValueError('the batch DAG requires explicit analytics settings')
    root = Path(paths.output)
    root.mkdir(parents=True, exist_ok=False)
    prepare_batch(Path(paths.config), root / 'prepared')
    return {'plan': str(root / 'prepared/plan.json'), 'execution_dir': str(root / 'execution'),
            'dbt_project': paths.dbt_project, 'dbt_python': paths.dbt_python}


def load(references):
    execute_batch(Path(references['plan']), Path(references['execution_dir']))
    return references


def run_stage(references, stage):
    import gnr_stage

    gnr_stage.run_stage(references['plan'], references['execution_dir'],
                        references['dbt_project'], stage,
                        dbt_python=references['dbt_python'])
    return references
