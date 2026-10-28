"""Public measurement output must contain no private strings."""
import contextlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_codex_workflow import sample_index
from test_validation_host import TempCase

SCRIPT = Path(__file__).parent / 'integration' / 'run_preparation_measurement.py'


class PreparationMeasurementTests(unittest.TestCase):
    def helper(self):
        self.assertTrue(SCRIPT.is_file(), 'measurement helper is missing')
        spec = importlib.util.spec_from_file_location('preparation_measurement', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_public_summary_drops_private_fields(self):
        m = self.helper()
        data = {'preparation': {'status': 'prepared', 'version': '1.7.4985 rev1269',
            'files': 10, 'path': 'PRIVATE', 'r2': {'downloaded': 10, 'cached': 0,
            'listedBytes': 1000, 'secret': 'PRIVATE'},
            'timings': {'fetchSeconds': 2.5, 'snapshotCopySeconds': 0.1,
            'snapshotHashSeconds': 0.2, 'snapshotTotalSeconds': 0.4,
            'totalSeconds': 2.9, 'secret': 'PRIVATE'}},
            'mods': {'count': 1, 'files': 6, 'bytes': 123}, 'snapshotReused': True,
            'validation': {'status': 'passed', 'executionStatus': 'completed',
            'fidelity': 'qualified', 'modOrder': {'matches': True, 'actual': ['PRIVATE']},
            'timings': {'totalSeconds': 5.0}, 'reasons': [{'detail': 'PRIVATE'}]}}
        result = m.public_summary(data)
        self.assertTrue(result['ok'])
        self.assertEqual(result['preparation']['timings']['fetchSeconds'], 2.5)
        self.assertEqual(result['mods'], {'count': 1, 'files': 6, 'bytes': 123})
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertEqual(m.public_summary(result), result)

    def test_invalid_values_cannot_become_public_or_claim_success(self):
        m = self.helper()
        result = m.public_summary({'ok': True, 'snapshotReused': 'true',
            'preparation': {'status': 'PRIVATE', 'version': 'PRIVATE', 'files': True,
            'r2': {'downloaded': -1, 'cached': 'PRIVATE'},
            'timings': {'fetchSeconds': math.nan, 'totalSeconds': True}},
            'validation': {'status': 'PRIVATE', 'fidelity': 'PRIVATE',
                           'executionStatus': 'PRIVATE', 'modOrderMatches': 'true'}})
        self.assertFalse(result['ok'])
        self.assertEqual(result['preparation']['r2'], {})
        self.assertEqual(result['preparation']['timings'], {})
        self.assertNotIn('PRIVATE', json.dumps(result, allow_nan=False))

    def test_publish_rechecks_file_instead_of_echoing_it(self):
        m = self.helper()
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'safe-summary.json').write_text(
                json.dumps({'ok': True, 'secret': 'PRIVATE'}))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = m.main(['publish', '--root', directory])
            self.assertEqual(code, 0)
            self.assertFalse(json.loads(output.getvalue())['ok'])
            self.assertNotIn('PRIVATE', output.getvalue())

    def test_rejected_repeat_preparation_cannot_publish_old_success(self):
        m = self.helper()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'game-snapshot').mkdir()
            previous = {'preparation': {'status': 'prepared'}, 'snapshotReused': True,
                'validation': {'status': 'passed', 'executionStatus': 'completed',
                               'fidelity': 'qualified', 'modOrderMatches': True}}
            (root / 'safe-summary.json').write_text(json.dumps(previous))
            with self.assertRaises(m.cw.WorkflowError):
                m.main(['prepare', '--root', directory])
            self.assertEqual(m.read_summary(root), m.public_summary({}))

    def test_a_run_rejects_scope_expansion_before_starting_host(self):
        m = self.helper()
        for extra in ({'levels': ['A', 'C']}, {'map': {}}, {'tests': []}):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                request = {'levels': ['A'], 'official': ['Core'],
                           'language': 'English', 'mods': [{'packageId': 'test'}]}
                request.update(extra)
                (root / 'request.json').write_text(json.dumps(request))
                with patch.object(m.vh, 'run_validation', side_effect=AssertionError('host started')):
                    with self.assertRaises(m.cw.WorkflowError):
                        m.validate_a(root, Path('worker'))


class PreparationMeasurementFlowTests(TempCase):
    helper = PreparationMeasurementTests.helper

    def test_synthetic_prepare_reuse_and_credential_free_run(self):
        m = self.helper()
        archive = self.root / 'index.zip'
        sample_index(archive)
        index_bytes = archive.read_bytes()
        about = b'<ModMetaData><packageId>brrainz.harmony</packageId></ModMetaData>'

        class FakeR2:
            def list_prefix(self, prefix):
                if prefix == 'Workshop/2009463077/':
                    return [{'key': prefix + 'About/About.xml', 'size': len(about)}]
                if prefix == 'Game-Linux/':
                    return [{'key': prefix + 'Version.txt', 'size': 12}]
                raise AssertionError('unexpected prefix')

            def get(self, key, dest, size=None, *, expected_size=None, refresh=False):
                dest.parent.mkdir(parents=True, exist_ok=True)
                if key == 'rimworld-mod-index.zip':
                    dest.write_bytes(index_bytes)
                elif key == 'Workshop/2009463077/About/About.xml':
                    dest.write_bytes(about)
                elif key == 'Game-Linux/Version.txt':
                    return 'cached'
                else:
                    raise AssertionError('unexpected key')
                return 'downloaded'

        with patch.object(m.cw, 'r2_client', return_value=FakeR2()):
            self.assertEqual(m.main(['prepare', '--root', str(self.root)]), 0)
        prepared = m.read_summary(self.root)
        self.assertTrue(prepared['snapshotReused'])
        self.assertEqual(prepared['mods']['count'], 1)
        self.assertEqual(prepared['preparation']['r2']['cached'], 1)
        self.assertFalse(prepared['ok'])

        def fake_worker(*args, **kwargs):
            self.assertNotIn('AWS_SECRET_ACCESS_KEY', os.environ)
            self.assertNotIn('R2_ENDPOINT', os.environ)
            return {'status': 'passed', 'executionStatus': 'completed', 'fidelity': 'qualified',
                    'modOrder': {'matches': True}, 'timings': {'totalSeconds': 1.0}}

        with patch.dict(os.environ, {'AWS_SECRET_ACCESS_KEY': 'PRIVATE', 'R2_ENDPOINT': 'PRIVATE'}), \
             patch.object(m.vh, 'run_validation', side_effect=fake_worker):
            self.assertEqual(m.main(['run', '--root', str(self.root)]), 0)
            self.assertEqual(os.environ['AWS_SECRET_ACCESS_KEY'], 'PRIVATE')
        final = m.read_summary(self.root)
        self.assertTrue(final['ok'])
        self.assertNotIn('PRIVATE', json.dumps(final))


if __name__ == '__main__':
    unittest.main()
