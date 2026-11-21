"""Unit tests for the development-only map comparison statistics (no game files needed)."""
from pathlib import Path
import random
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
        rng = random.Random(1)
        def run(**extra):
            return {'a': round(rng.gauss(100, 3)), 'b': round(rng.gauss(500, 20)), 'fixed': 8, **extra}
        official = [run() for _ in range(5)]
        official[1]['rare'] = 150
        same = [run() for _ in range(5)]
        same[2]['rare'] = 140
        same[2]['fixed'] = 205  # one unusual run on one side alone is not a difference
        rows, differing, test = co.compare_distributions(same, official)
        self.assertEqual(differing, [])
        self.assertEqual((test['splits'], test['exact'], test['canDetect']), (252, True, True))
        self.assertGreaterEqual(test['pValue'], co.MAP_ALPHA)
        self.assertFalse(rows['rare']['judged'])
        self.assertIn('rare (sum of intermittent kinds)', rows)
        shifted = [dict(r, a=r['a'] + 30) for r in same]
        self.assertEqual(co.compare_distributions(shifted, official)[1], ['a'])
        # Always present on one side, never on the other: judged even though it is 0 somewhere,
        # and even a single extra thing in every run is a difference.
        for count in (1, 3):
            added = [dict(r, mod=count) for r in same]
            self.assertEqual(co.compare_distributions(added, official)[1], ['mod'])

    def test_permutation_test_keeps_its_false_alarm_rate(self):
        # Identical distributions, 12 independent metrics, 5 + 5 runs: how often is anything reported?
        rng = random.Random(7)
        alarms = 0
        trials = 200
        for _ in range(trials):
            columns = {f'm{k}': [round(rng.gauss(100, 5)) for _ in range(10)] for k in range(12)}
            alarms += co.permutation_test(columns, 5)[1]['pValue'] < co.MAP_ALPHA
        self.assertLessEqual(alarms / trials, 0.09)
        self.assertGreater(alarms, 0)

    def test_permutation_test_finds_a_large_shift_in_one_metric(self):
        rng = random.Random(8)
        found = 0
        for _ in range(40):
            columns = {f'm{k}': [round(rng.gauss(100, 5)) for _ in range(10)] for k in range(12)}
            columns['m3'] = [v + 30 if i < 5 else v for i, v in enumerate(columns['m3'])]
            rows, summary = co.permutation_test(columns, 5)
            found += rows['m3']['adjustedP'] < co.MAP_ALPHA
        self.assertGreaterEqual(found, 32)

    def test_permutation_test_edge_cases(self):
        self.assertEqual(co.permutation_test({'same': [4] * 10}, 5)[1]['pValue'], 1.0)
        # 3 + 3 runs: even a complete separation is 2 of 20 relabellings, so nothing can be shown.
        rows, summary = co.permutation_test({'m': [0, 0, 0, 1, 1, 1]}, 3)
        self.assertFalse(summary['canDetect'])
        # 10 + 10 runs: random relabellings with a fixed seed, so the result repeats.
        columns = {'m': [0] * 10 + [1] * 10, 'n': list(range(20))}
        first, second = co.permutation_test(columns, 10), co.permutation_test(columns, 10)
        self.assertEqual(first, second)
        self.assertEqual((first[1]['splits'], first[1]['exact'], first[1]['canDetect']), (co.RANDOM_SPLITS, False, True))
        self.assertLess(first[0]['m']['adjustedP'], co.MAP_ALPHA)
        with self.assertRaises(ValueError):
            co.permutation_test({'m': [1, 2, 3], 'n': [1, 2]}, 1)

    def test_equivalence_needs_a_generated_map_in_every_run(self):
        mods = '[RWMT-PROBE] mods core'
        world = '[RWMT-PROBE] map world seed=rwmt tile=1'
        generated = {'errors': [], 'probes': [mods, world, '[RWMT-PROBE] map things count=10 sha=ab']}
        stopped = {'errors': ['load failed'], 'probes': [mods]}

        def summary(product, official):
            return co.summarize_map_runs('case', {'product': product, 'official': official}, ['passed'] * len(product))

        # Two runs per side cannot show a difference, so they cannot show equivalence either.
        self.assertFalse(summary([generated] * 2, [generated] * 2)['equivalent'])
        self.assertTrue(summary([generated] * 5, [generated] * 5)['equivalent'])
        # Both sides stopping before the map agree on setup, errors and (no) counts.
        row = summary([stopped] * 2, [stopped] * 2)
        self.assertEqual(row['mapGeneratedInAllRuns'], {'product': False, 'official': False})
        self.assertFalse(row['equivalent'])
        self.assertFalse(summary([generated, dict(generated, probes=[mods, world])], [generated] * 2)['equivalent'])
        self.assertFalse(summary([], [])['equivalent'])


if __name__ == '__main__':
    unittest.main()
