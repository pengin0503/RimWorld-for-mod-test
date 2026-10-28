import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).parent / 'integration' / 'benchmark_r2_transport.py'


class BenchmarkTests(unittest.TestCase):
    def helper(self):
        self.assertTrue(SCRIPT.exists(), 'transport benchmark is missing')
        spec = importlib.util.spec_from_file_location('r2_benchmark', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_selection_is_small_core_only_and_requires_32_objects(self):
        m = self.helper()
        items = [{'key': 'Game-Linux/Version.txt', 'size': 1}] + [
            {'key': f'Game-Linux/Data/Core/Defs/{n:02}.xml', 'size': 1} for n in range(40)]
        items += [{'key': 'Game-Linux/Data/Anomaly/Defs/a.xml', 'size': 1},
                  {'key': 'Game-Linux/Data/Core/Defs/huge.xml', 'size': 65537}]
        sample = m.select_sample(items)
        self.assertEqual(len(sample), 32)
        self.assertEqual(sum(x['size'] for x in sample), 32)
        self.assertEqual(sample[0]['key'], 'Game-Linux/Version.txt')
        self.assertFalse(any('Anomaly' in x['key'] or 'huge' in x['key'] for x in sample))
        with self.assertRaises(m.ra.AssetError):
            m.select_sample(items[:10])

    def test_identical_bytes_are_checked_across_six_fresh_trials(self):
        m = self.helper()
        class Client:
            def __init__(self, **kwargs):
                self.transport = kwargs['transport']
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def list_prefix(self, prefix):
                return [{'key': 'Game-Linux/Version.txt', 'size': 1}] + [
                    {'key': f'Game-Linux/Data/Core/Defs/{n}.xml', 'size': 1} for n in range(31)]
            def get(self, key, dest, size, **kwargs):
                if dest.exists():
                    raise AssertionError('timed destination already exists')
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(b'x')
                return 'downloaded'
        with tempfile.TemporaryDirectory() as directory, patch.object(m.ra, 'R2', Client):
            result = m.benchmark(Path(directory), 'endpoint')
            self.assertTrue(result['ok'])
            self.assertEqual([t['transport'] for t in result['trials']],
                             ['cli', 'sdk', 'sdk', 'cli', 'cli', 'sdk'])
            self.assertEqual(result['files'], 32)
            self.assertEqual(result['bytesPerTrial'], 32)
            self.assertNotIn('Game-Linux', json.dumps(result))

    def test_hash_mismatch_fails_instead_of_reporting_speed(self):
        m = self.helper()
        class Client:
            def __init__(self, **kwargs): self.mode = kwargs['transport']
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def list_prefix(self, prefix):
                return [{'key': 'Game-Linux/Version.txt', 'size': 1}] + [
                    {'key': f'Game-Linux/Data/Core/Defs/{n}.xml', 'size': 1} for n in range(31)]
            def get(self, key, dest, size, **kwargs):
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(b'x' if self.mode == 'cli' else b'y')
                return 'downloaded'
        with tempfile.TemporaryDirectory() as directory, patch.object(m.ra, 'R2', Client):
            with self.assertRaises(m.ra.AssetError):
                m.benchmark(Path(directory), 'endpoint')

    def test_public_summary_cannot_forward_private_data(self):
        m = self.helper()
        result = m.safe_summary({'ok': True, 'secret': 'PRIVATE', 'files': 'PRIVATE',
            'trials': [{'transport': 'PRIVATE', 'seconds': float('nan')}], 'hashesMatch': True})
        self.assertFalse(result['ok'])
        self.assertNotIn('PRIVATE', json.dumps(result, allow_nan=False))
