import json
import tempfile
import unittest
from pathlib import Path

from pusher.config import ConfigStore
from pusher.models import AppError


class ConfigTests(unittest.TestCase):
    def test_round_trip_and_export_contains_no_token(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ConfigStore(Path(folder) / 'config.json')
            settings = {'remote': 'https://github.com/a/b.git', 'tag': 'v1', 'token': 'must-not-be-written'}
            store.save(settings)
            self.assertEqual(store.load(), settings)
            export = Path(folder) / 'export.json'
            store.export(export, {'remote': settings['remote'], 'tag': settings['tag']})
            self.assertNotIn('token', export.read_text(encoding='utf-8'))

    def test_import_rejects_unknown_format(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.json'
            path.write_text(json.dumps({'version': 99, 'settings': {}}), encoding='utf-8')
            with self.assertRaises(AppError):
                ConfigStore(path).import_file(path)

    def test_missing_config_is_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(ConfigStore(Path(folder) / 'missing.json').load(), {})
