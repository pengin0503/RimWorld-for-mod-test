"""Unit tests for the development-only map comparison (no game files needed)."""
from pathlib import Path
import sys
import tempfile
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

    def test_content_and_seed_lines(self):
        probes = ['[RWMT-PROBE] mods core', '[RWMT-PROBE] map seeds nextGenSeed=replaced layoutRoomSeeds=3 salt=2',
                  '[RWMT-PROBE] map world seed=rwmt tile=1', '[RWMT-PROBE] map terrain sha=ab',
                  '[RWMT-PROBE] map things count=10 sha=cd', '[RWMT-PROBE] map pawns Colonist@1,2']
        self.assertEqual(co.map_seeds(probes), ('replaced', '3', '2'))
        self.assertEqual(co.map_content(probes), probes[3:])
        self.assertIsNone(co.map_seeds(probes[:1]))

    def test_content_difference_names_what_differs(self):
        product = ['[RWMT-PROBE] map things count=10 sha=aa', '[RWMT-PROBE] map thing-count Steel=4',
                   '[RWMT-PROBE] map terrain sha=11']
        official = ['[RWMT-PROBE] map things count=11 sha=bb', '[RWMT-PROBE] map thing-count Steel=4',
                    '[RWMT-PROBE] map thing-count Wood=1', '[RWMT-PROBE] map terrain sha=11']
        diff = co.content_difference(product, official)
        self.assertEqual(diff['metrics'], {'thing-count Wood': [0, 1], 'things count': [10, 11]})
        self.assertEqual(diff['metricsDiffering'], 2)
        self.assertEqual(diff['otherLines'], [])
        diff = co.content_difference(['[RWMT-PROBE] map terrain sha=11'], ['[RWMT-PROBE] map terrain sha=12'])
        self.assertEqual((diff['metrics'], diff['otherLines']),
                         ({}, ['[RWMT-PROBE] map terrain sha=11', '[RWMT-PROBE] map terrain sha=12']))

    def test_salted_fixture_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp) / 'built' / 'mapprobe'
            (probe / 'About').mkdir(parents=True)
            (probe / 'About' / 'About.xml').write_text('<ModMetaData/>', encoding='utf-8')
            run_dir = Path(tmp) / 'run2'
            run_dir.mkdir()
            salted = co.map_salt_fixture(probe, run_dir, 2)
            self.assertEqual(salted.name, 'mapprobe')
            self.assertEqual((salted / 'Salt.txt').read_text(encoding='utf-8'), '2\n')
            self.assertTrue((salted / 'About' / 'About.xml').is_file())
            self.assertFalse((probe / 'Salt.txt').exists())

    def test_equivalence_needs_the_same_map_in_every_run(self):
        mods = '[RWMT-PROBE] mods core'
        world = '[RWMT-PROBE] map world seed=rwmt tile=1'

        def generated(salt, things='ab', seeds='replaced'):
            return {'errors': [], 'probes': [mods, f'[RWMT-PROBE] map seeds nextGenSeed={seeds} layoutRoomSeeds=3 salt={salt}',
                                             world, f'[RWMT-PROBE] map things count=10 sha={things}{salt}']}

        def summary(product, official):
            return co.summarize_map_runs('case', {'product': product, 'official': official}, ['passed'] * len(product))

        runs = [generated(i + 1) for i in range(3)]
        row = summary(runs, [dict(r) for r in runs])
        self.assertTrue(row['equivalent'])
        self.assertEqual((row['runsMatching'], row['distinctMaps'], row['deterministicSeeds']), (3, 3, True))
        # One run whose two maps differ.
        other = list(runs)
        other[1] = generated(2, things='zz')
        row = summary(runs, other)
        self.assertFalse(row['equivalent'])
        self.assertEqual([d['run'] for d in row['runsDiffering']], [2])
        # The seeds were not replaced, or a run used another run's salt.
        missing = [generated(i + 1, seeds='missing') for i in range(3)]
        self.assertFalse(summary(missing, missing)['equivalent'])
        reused = [generated(1)] * 3
        self.assertFalse(summary(reused, reused)['deterministicSeeds'])
        # One run is not enough to compare; both sides stopping before the map agree on everything else.
        self.assertFalse(summary(runs[:1], runs[:1])['equivalent'])
        stopped = {'errors': ['load failed'], 'probes': [mods]}
        row = summary([stopped] * 2, [stopped] * 2)
        self.assertEqual(row['mapGeneratedInAllRuns'], {'product': False, 'official': False})
        self.assertFalse(row['equivalent'])
        self.assertFalse(summary(runs, runs[:2])['equivalent'])
        self.assertFalse(summary([], [])['equivalent'])

if __name__ == '__main__':
    unittest.main()
