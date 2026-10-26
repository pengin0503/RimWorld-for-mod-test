"""Unit tests for the development-only map comparison statistics (no game files needed)."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'experiments' / 'official-comparison'))
import compare_official as co  # noqa: E402


class MapMetricTests(unittest.TestCase):
    def test_probe_lines_become_metrics(self):
        lines = ['[RWMT-PROBE] map category Item=1665', '[RWMT-PROBE] map things count=15561 sha=ab12',
                 '[RWMT-PROBE] map terrain-cells Sand=22000', '[RWMT-PROBE] map roofed-cells=1800',
                 '[RWMT-PROBE] map thing-count RWMT_Monolith=3', '[RWMT-PROBE] map terrain sha=ffff']
        self.assertEqual(co.map_metrics(lines), {'category Item': 1665, 'things count': 15561, 'terrain-cells Sand': 22000,
                                                 'roofed-cells': 1800, 'thing-count RWMT_Monolith': 3})

    def test_distributions(self):
        official = [{'a': 100, 'rare': 0, 'fixed': 8}, {'a': 104, 'rare': 150, 'fixed': 8}, {'a': 98, 'rare': 0, 'fixed': 8}]
        same = [{'a': 101, 'rare': 0, 'fixed': 8}, {'a': 99, 'rare': 0, 'fixed': 8}, {'a': 103, 'rare': 140, 'fixed': 205}]
        rows, outside = co.compare_distributions(same, official)
        self.assertEqual(outside, [])
        self.assertFalse(rows['rare']['judged'])
        self.assertIn('rare (sum of intermittent kinds)', rows)
        shifted = [dict(run, a=run['a'] + 30) for run in same]
        self.assertEqual(co.compare_distributions(shifted, official)[1], ['a'])
        # Always present on one side, never on the other: judged even though it is 0 somewhere.
        added = [dict(run, mod=3) for run in same]
        self.assertEqual(co.compare_distributions(added, official)[1], ['mod'])

    def test_equivalence_needs_a_generated_map_in_every_run(self):
        mods = '[RWMT-PROBE] mods core'
        world = '[RWMT-PROBE] map world seed=rwmt tile=1'
        generated = {'errors': [], 'probes': [mods, world, '[RWMT-PROBE] map things count=10 sha=ab']}
        stopped = {'errors': ['load failed'], 'probes': [mods]}

        def summary(product, official):
            return co.summarize_map_runs('case', {'product': product, 'official': official}, ['passed'] * len(product))

        self.assertTrue(summary([generated] * 2, [generated] * 2)['equivalent'])
        # Both sides stopping before the map agree on setup, errors and (no) counts.
        row = summary([stopped] * 2, [stopped] * 2)
        self.assertEqual(row['mapGeneratedInAllRuns'], {'product': False, 'official': False})
        self.assertFalse(row['equivalent'])
        self.assertFalse(summary([generated, dict(generated, probes=[mods, world])], [generated] * 2)['equivalent'])
        self.assertFalse(summary([], [])['equivalent'])


if __name__ == '__main__':
    unittest.main()
