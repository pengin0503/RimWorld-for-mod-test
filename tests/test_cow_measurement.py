"""The experiment must measure shared extents, not double-count st_blocks."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'experiments/cow-measurement/measure.py'

class CowMeasurementTests(unittest.TestCase):
    def helper(self):
        self.assertTrue(SCRIPT.is_file(), 'COW measurement is missing')
        spec = importlib.util.spec_from_file_location('cow_measure', SCRIPT)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        return m

    def test_physical_union_counts_shared_ranges_once(self):
        m = self.helper()
        self.assertEqual(m.union_bytes([(100, 20), (100, 20), (110, 20), (200, 10)]), 40)
        self.assertEqual(m.union_bytes([]), 0)
        with self.assertRaises(ValueError): m.union_bytes([(0, 1024)])

    def test_copy_mode_is_verified_and_independent(self):
        m = self.helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'source'; source.mkdir()
            (source / 'payload').write_bytes(b'0123456789' * 1024)
            hashes = m.hashes(source)
            modes = m.stage(source, root / 'baseline', hashes, force_copy=True)
            m.stage(source, root / 'target', hashes, force_copy=True)
            self.assertEqual(modes, {'copy': 1, 'reflink': 0})
            self.assertTrue(m.isolated(source, root / 'baseline', root / 'target', hashes))

    def test_stale_hash_blocks_even_when_copy_finishes(self):
        m = self.helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'source'; source.mkdir()
            (source / 'payload').write_bytes(b'old')
            hashes = m.hashes(source)
            (source / 'payload').write_bytes(b'new')
            with self.assertRaises(m.vh.Blocked):
                m.stage(source, root / 'target', hashes, force_copy=True)

    def test_invalid_physical_map_cannot_claim_savings(self):
        m = self.helper()
        with self.assertRaises(ValueError): m.extent_ranges(b'broken')

if __name__ == '__main__': unittest.main()
