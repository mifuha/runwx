"""Batch coordination tests use synthetic inputs and the real safe loader."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import socket
from unittest.mock import Mock
from urllib.parse import urlencode

from google.cloud import bigquery
import pytest

from runwx.main import main
from runwx.adapters.bigquery.gnr_sample_load import SCHEMA
from runwx.services.gnr_batch import BatchError, execute_batch, prepare_batch


def write_json(path, value):
    path.write_text(json.dumps(value))


@pytest.fixture
def batch(tmp_path, monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **kw: pytest.fail("unexpected network"))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: pytest.fail("unexpected DNS"))
    editions = []
    for year, race_id, day in [(2019, 881, '2019-09-08'), (2022, 1149, '2022-09-11')]:
        folder = tmp_path / str(year)
        folder.mkdir()
        def results(offset):
            return [{"idResult": i + offset + 1, "idRace": race_id, "idRaceCategory": 1,
                     "wheelchair": 0, "eventRace": "Mass", "gunChip": "C",
                     "timeFinish": f"01:{(4000 + offset // 2 + i) % 3600 // 60:02}:{(4000 + offset // 2 + i) % 60:02}"}
                    for i in range(1000)]
        race = {"success": True, "raceDetail": {"idRace": race_id, "raceDate": day+'T00:00:00',
                                               "distanceInKm": 21.1},
                "resultMen": results(0), "resultWomen": results(1000)}
        categories = [{"value": "1", "text": "Orange B"}]
        for name, value in [('race', race), ('categories', categories)]:
            path = folder / f'{name}.json'
            write_json(path, value)
            capture = {'sha256': sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size}
            if name == 'race':
                url = f'https://results.greatrun.org/leaderboard/getleaderboardraceresults?raceId={race_id}&eventCategory=Mass'
                capture.update(requested_url=url, returned_url=url, status=200)
            else:
                capture['url'] = f'https://results.greatrun.org/utility/getracecategory?selectedIdRace={race_id}'
            write_json(folder / f'{name}.json.capture.json', capture)
        weather = {"timezone": "GMT", "utc_offset_seconds": 0, "latitude": 55.0, "longitude": -1.5,
                   "hourly_units": {"time": "iso8601", "temperature_2m": "°C", "wind_speed_10m": "m/s",
                                    "precipitation": "mm", "relative_humidity_2m": "%"},
                   "hourly": {"time": [f'{day}T{h:02}:00' for h in range(24)],
                              "temperature_2m": [12.0]*24, "wind_speed_10m": [2.0]*24,
                              "precipitation": [0.0]*24, "relative_humidity_2m": [60.0]*24}}
        write_json(folder/'weather.json', weather)
        params = {"latitude": 54.984, "longitude": -1.62, "start_date": day, "end_date": day,
                  "hourly": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
                  "models": "era5", "timezone": "UTC", "temperature_unit": "celsius",
                  "wind_speed_unit": "ms", "precipitation_unit": "mm"}
        raw = (folder/'weather.json').read_bytes()
        write_json(folder/'request.json', {'params': params, 'provider': 'Open-Meteo', 'dataset': 'ERA5',
                                         'status': 200, 'sha256': sha256(raw).hexdigest(), 'bytes': len(raw),
                                         'url': 'https://archive-api.open-meteo.com/v1/archive?' + urlencode(params)})
        editions.append({'year': year, 'race_json': f'{year}/race.json',
                         'categories_json': f'{year}/categories.json',
                         'weather_json': f'{year}/weather.json', 'weather_request': f'{year}/request.json'})
    config = tmp_path/'batch.json'
    write_json(config, {'version': 1, 'project': 'runwx-learning-mifuha', 'editions': editions})
    return config


class Warehouse:
    def __init__(self):
        self.rows = {}
        self.loads = []
        self.fail_table = None
        self.api = Mock(spec=bigquery.Client)
        self.api.project = 'runwx-learning-mifuha'
        self.api.get_table.side_effect = self.get_table
        self.api.query.side_effect = self.query
        self.api.load_table_from_file.side_effect = self.load

    def get_table(self, table, **kwargs):
        project, dataset, table_id = table.split('.')
        return bigquery.Table.from_api_repr({
            'tableReference': {'projectId': project, 'datasetId': dataset, 'tableId': table_id},
            'location': 'europe-west1', 'type': 'TABLE', 'schema': {'fields': SCHEMA},
        })

    def query(self, sql, **kwargs):
        table = re.search(r'FROM `([^`]+)`', sql).group(1)
        values = deepcopy(self.rows.get(table, []))
        return Mock(job_id=f'query_{self.api.query.call_count}', total_bytes_processed=50000,
                    total_bytes_billed=10485760,
                    result=Mock(return_value=[{'row_json': json.dumps(row)} for row in values]))

    def load(self, source, destination, **kwargs):
        self.loads.append(destination)
        config = kwargs['job_config']
        assert config.write_disposition == 'WRITE_EMPTY' and config.create_disposition == 'CREATE_NEVER'
        if destination == self.fail_table:
            raise TimeoutError('submission outcome uncertain')
        assert destination not in self.rows
        self.rows[destination] = [json.loads(line) for line in source.read().splitlines()]
        return Mock(job_id=kwargs['job_id'])


def test_prepare_multiple_editions_deterministically_offline(batch, tmp_path, monkeypatch):
    monkeypatch.setattr(bigquery, 'Client', lambda **kw: pytest.fail('credentials during prepare'))
    first, second = tmp_path/'first', tmp_path/'second'
    result = prepare_batch(batch, first)
    prepare_batch(batch, second)
    assert result['sample_count'] == 2000 and result['destination_existence'] == 'not_checked'
    assert (first/'plan.json').read_bytes() == (second/'plan.json').read_bytes()
    plan = json.loads((first/'plan.json').read_text())
    assert [e['year'] for e in plan['editions']] == [2019, 2022]
    for entry in plan['editions']:
        assert (first/entry['export_file']).read_bytes() == (second/entry['export_file']).read_bytes()
        assert entry['summary']['timing_counts'] == {'chip': 1000}
        assert entry['summary']['sample_label'] == 'Top 1,000 only*'
        assert entry['summary']['sample_count'] == 1000
    with pytest.raises(FileExistsError):
        prepare_batch(batch, first)


def test_collect_all_preparation_errors_and_leave_no_plan(batch, tmp_path):
    (tmp_path/'2019/race.json').write_text('{}')
    (tmp_path/'2022/weather.json').unlink()
    with pytest.raises(BatchError, match='2 edition'):
        prepare_batch(batch, tmp_path/'invalid')
    record = json.loads((tmp_path/'invalid/preparation.json').read_text())
    assert {e['year'] for e in record['errors']} == {2019, 2022}
    assert not (tmp_path/'invalid/plan.json').exists()
    assert not list((tmp_path/'invalid').glob('*.ndjson'))


@pytest.mark.parametrize('change', ['duplicate', 'unknown', 'foreign_table', 'wrong_capture', 'malformed_capture_url'])
def test_bad_config_and_qualification_fail_offline(batch, tmp_path, change):
    config = json.loads(batch.read_text())
    if change == 'duplicate': config['editions'].append(config['editions'][0])
    if change == 'unknown': config['editions'][0]['year'] = 2021
    if change == 'foreign_table': config['editions'][0]['table_id'] = 'other_project.staging.table'
    if change == 'wrong_capture':
        p = tmp_path/'2019/race.json.capture.json'
        capture = json.loads(p.read_text())
        capture['returned_url'] = capture['returned_url'].replace('881', '1149')
        write_json(p, capture)
    if change == 'malformed_capture_url':
        p = tmp_path/'2019/race.json.capture.json'
        capture = json.loads(p.read_text())
        capture['returned_url'] = 881
        write_json(p, capture)
    write_json(batch, config)
    with pytest.raises(BatchError):
        prepare_batch(batch, tmp_path/'invalid')
    assert not (tmp_path/'invalid/plan.json').exists()


@pytest.mark.parametrize('changed', ['config', 'race', 'capture', 'weather_request', 'export', 'plan'])
def test_any_changed_input_blocks_every_load_before_credentials(batch, tmp_path, monkeypatch, changed):
    prepared = tmp_path/'prepared'
    prepare_batch(batch, prepared)
    paths = {'config': batch, 'race': tmp_path/'2022/race.json',
             'capture': tmp_path/'2022/categories.json.capture.json',
             'weather_request': tmp_path/'2022/request.json', 'export': prepared/'2022.ndjson',
             'plan': prepared/'plan.json'}
    with paths[changed].open('a') as stream: stream.write(' ')
    monkeypatch.setattr(bigquery, 'Client', lambda **kw: pytest.fail('client created before complete validation'))
    with pytest.raises(BatchError):
        execute_batch(prepared/'plan.json', tmp_path/'run')
    record = json.loads((tmp_path/'run/execution.json').read_text())
    assert record['stage'] == 'preflight' and record['status'] == 'failed'


def test_batch_rerun_verifies_rows_and_does_not_load_again(batch, tmp_path):
    prepare_batch(batch, tmp_path/'prepared')
    warehouse = Warehouse()
    plan = tmp_path/'prepared/plan.json'
    first = execute_batch(plan, tmp_path/'run1', client=warehouse.api)
    second = execute_batch(plan, tmp_path/'run2', client=warehouse.api)
    assert first['status'] == second['status'] == 'loaded_verified'
    assert len(warehouse.loads) == 2
    assert all(e['status'] == 'already_present_verified' for e in second['editions'])
    assert first['analytical_status'] == 'not_run'
    warehouse.api.close.assert_not_called()
    with pytest.raises(FileExistsError):
        execute_batch(plan, tmp_path/'run1', client=warehouse.api)


def test_failed_submission_retains_job_id_and_rerun_verifies_previous_load(batch, tmp_path):
    prepare_batch(batch, tmp_path/'prepared')
    plan = tmp_path/'prepared/plan.json'
    entries = json.loads(plan.read_text())['editions']
    warehouse = Warehouse()
    warehouse.fail_table = entries[1]['table_id']
    with pytest.raises(BatchError, match='submission outcome uncertain'):
        execute_batch(plan, tmp_path/'run1', client=warehouse.api)
    record = json.loads((tmp_path/'run1/execution.json').read_text())
    assert record['editions'][0]['status'] == 'loaded_verified'
    assert record['editions'][1]['status'] == 'failed'
    assert record['editions'][1]['planned_load_job_id'] == entries[1]['planned_load_job_id']
    assert len(warehouse.loads) == 2  # No automatic retry.
    # The uncertain request actually landed. Recovery must inspect warehouse contents.
    warehouse.rows[entries[1]['table_id']] = [json.loads(line) for line in
                                            (plan.parent/'2022.ndjson').read_bytes().splitlines()]
    warehouse.fail_table = None
    result = execute_batch(plan, tmp_path/'run2', client=warehouse.api)
    assert all(e['status'] == 'already_present_verified' for e in result['editions'])
    assert len(warehouse.loads) == 2


def test_conflict_stops_remaining_editions_without_overwrite(batch, tmp_path):
    prepare_batch(batch, tmp_path/'prepared')
    plan = tmp_path/'prepared/plan.json'
    entries = json.loads(plan.read_text())['editions']
    warehouse = Warehouse()
    row = json.loads((plan.parent/'2019.ndjson').read_text().splitlines()[0])
    warehouse.rows[entries[0]['table_id']] = [row]  # Incomplete existing snapshot.
    with pytest.raises(BatchError, match='stored rows differ'):
        execute_batch(plan, tmp_path/'run', client=warehouse.api)
    record = json.loads((tmp_path/'run/execution.json').read_text())
    assert [e['status'] for e in record['editions']] == ['failed', 'not_run']
    assert warehouse.loads == []


def test_batch_cli_prepare_and_failing_execute_have_clear_exit_status(batch, tmp_path, capsys):
    main(['batch', 'prepare', str(batch), '--output', str(tmp_path/'prepared')])
    assert json.loads(capsys.readouterr().out)['edition_count'] == 2
    with (tmp_path/'2019/race.json').open('a') as stream: stream.write(' ')
    with pytest.raises(SystemExit) as exc:
        main(['batch', 'execute', str(tmp_path/'prepared/plan.json'), '--output', str(tmp_path/'run')])
    assert exc.value.code == 1
    assert 'prepared input changed' in capsys.readouterr().err


def test_cli_execution_uses_one_client_and_closes_it(batch, tmp_path, monkeypatch, capsys):
    prepare_batch(batch, tmp_path/'prepared')
    warehouse = Warehouse()
    factory = Mock(return_value=warehouse.api)
    monkeypatch.setattr(bigquery, 'Client', factory)
    main(['batch', 'execute', str(tmp_path/'prepared/plan.json'), '--output', str(tmp_path/'run')])
    assert json.loads(capsys.readouterr().out)['status'] == 'loaded_verified'
    factory.assert_called_once_with(project='runwx-learning-mifuha', location='europe-west1')
    warehouse.api.close.assert_called_once()


def test_changed_source_date_is_not_qualified_by_a_matching_capture(batch, tmp_path):
    path = tmp_path/'2019/race.json'
    race = json.loads(path.read_text())
    race['raceDetail']['raceDate'] = '2019-09-09T00:00:00'
    write_json(path, race)
    capture_path = Path(str(path)+'.capture.json')
    capture = json.loads(capture_path.read_text())
    capture.update(sha256=sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)
    write_json(capture_path, capture)
    with pytest.raises(BatchError):
        prepare_batch(batch, tmp_path/'prepared')
    report = json.loads((tmp_path/'prepared/preparation.json').read_text())
    assert 'identity/date' in report['errors'][0]['error']


def test_explicit_corrected_destination_is_retained_in_plan(batch, tmp_path):
    config = json.loads(batch.read_text())
    config['editions'][0]['table_id'] = 'gnr_2019_abcdef123456'
    write_json(batch, config)
    prepare_batch(batch, tmp_path/'prepared')
    plan = json.loads((tmp_path/'prepared/plan.json').read_text())
    assert plan['editions'][0]['table_id'].endswith('.gnr_2019_abcdef123456')


@pytest.mark.parametrize('changed', ['CATALOG_BYTES', 'SCHEMA_BYTES'])
def test_catalog_and_schema_changes_invalidate_plan(batch, tmp_path, monkeypatch, changed):
    from runwx.services import gnr_batch

    prepare_batch(batch, tmp_path/'prepared')
    monkeypatch.setattr(gnr_batch, changed, b'changed contract')
    warehouse = Warehouse()
    with pytest.raises(BatchError, match='catalog or export schema changed'):
        execute_batch(tmp_path/'prepared/plan.json', tmp_path/'run', client=warehouse.api)
    warehouse.api.get_table.assert_not_called()
