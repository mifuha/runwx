"""Offline configuration checks and dbt compilation; no SQL execution."""

import json
from pathlib import Path
import re
import socket
from types import SimpleNamespace
import unittest

from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'runwx-offline-placeholder'
TABLE = f'{PROJECT}.runwx_staging.berlin_2018_research_bfd49c5c5d9c'


def reject(message):
    raise ValueError(message)


def environment(variables):
    env = Environment(extensions=['jinja2.ext.do'])
    env.globals.update(
        var=lambda key, default=None: variables.get(key, default),
        target=SimpleNamespace(project=PROJECT),
        modules=SimpleNamespace(re=re),
        exceptions=SimpleNamespace(raise_compiler_error=reject),
        # This macro returns only at its end; JSON preserves the returned value.
        config=lambda **kwargs: '', ref=lambda name: name,
    )
    env.globals['return'] = json.dumps
    return env


class ConfigurationTests(unittest.TestCase):
    def tables(self, value):
        env = environment({'berlin_research_tables': value})
        module = env.from_string((ROOT / 'macros/berlin_research.sql').read_text()).module
        return json.loads(module.berlin_research_tables())

    def test_empty_single_and_multiple_editions(self):
        for tables in ([], [TABLE], [TABLE, TABLE.replace('2018', '2012')]):
            with self.subTest(tables=tables):
                self.assertEqual(self.tables(tables), tables)

    def test_reject_invalid_lists_and_identifiers(self):
        for tables in (None, TABLE, {}, [None], [TABLE, TABLE], [TABLE] * 17,
                       [TABLE.replace(PROJECT, 'foreign-project')],
                       [TABLE.replace('2018', '2019')],
                       [TABLE.replace('2018', '2002')],
                       [TABLE + '`; select 1'], [TABLE.replace('research_', '')]):
            with self.subTest(tables=tables), self.assertRaises(ValueError):
                self.tables(tables)

    def test_reject_two_snapshots_of_same_edition(self):
        with self.assertRaisesRegex(ValueError, 'one Berlin snapshot'):
            self.tables([TABLE, TABLE.replace('bfd49c5c5d9c', 'aaaaaaaaaaaa')])

    def test_top_n_must_be_positive_integer(self):
        model = (ROOT / 'models/berlin/mart_berlin_edition_summary.sql').read_text()
        for n in (0, -1, True, 1.5, '20', None):
            with self.subTest(n=n), self.assertRaisesRegex(ValueError, 'positive integer'):
                environment({'top_n': n}).from_string(model).render()
        for n in (1, 20, 1000):
            environment({'top_n': n}).from_string(model).render()

    def test_unit_expected_rows_use_consistent_columns(self):
        import yaml

        fixtures = yaml.safe_load((ROOT / 'models/berlin/unit_tests.yml').read_text())
        for fixture in fixtures['unit_tests']:
            rows = fixture['expect']['rows']
            # dbt unions expected rows in their supplied column order.
            for row in rows[1:]:
                with self.subTest(fixture=fixture['name']):
                    self.assertEqual(list(row), list(rows[0]))


def compile_offline():
    import google.auth
    from google.auth.credentials import AnonymousCredentials
    from dbt.cli.main import dbtRunner
    import sqlglot

    def no_network(*args, **kwargs):
        raise AssertionError('Offline dbt compilation attempted network access')

    socket.socket.connect = no_network
    socket.create_connection = no_network
    # The adapter constructs a client during compilation. Supply a dummy identity;
    # never discover or refresh real ADC. All socket connections remain blocked.
    google.auth.default = lambda **kwargs: (AnonymousCredentials(), PROJECT)
    result = dbtRunner().invoke([
        '--no-partial-parse', '--no-populate-cache', 'compile', '--no-introspect',
        '--project-dir', str(ROOT), '--profiles-dir', str(ROOT), '--target', 'local',
        '--target-path', '/tmp/berlin-compile', '--log-path', '/tmp/berlin-logs',
        '--select', 'tag:berlin', '--vars', json.dumps({'berlin_research_tables': [TABLE]}),
    ])
    if not result.success:
        raise AssertionError(f'Offline dbt compilation failed: {result.exception}')
    models, tests = [], []
    for item in result.result.results:
        node = item.node
        sqlglot.parse_one(node.compiled_code, read='bigquery')
        (models if node.resource_type == 'model' else tests).append(node.name)
    if len(models) != 2 or len(tests) != 7:
        raise AssertionError(f'Missing compiled Berlin models/tests: {models}, {tests}')
    sqlglot.parse_one((ROOT / 'tests/fixtures/berlin_captured.sql').read_text(), read='bigquery')
    print('Compiled and syntax-checked 2 models / 7 data tests; SQL was not executed.')


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(ConfigurationTests))
    if not result.wasSuccessful():
        raise SystemExit(1)
    compile_offline()
