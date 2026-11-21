"""The automatic build qualification grants only what its stages showed (no game needed)."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
_spec = importlib.util.spec_from_file_location('qualify_build', REPO / 'experiments/official-comparison/qualify_build.py')
qb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qb)
import game_builds  # noqa: E402

VERSION = '1.7.6000 rev7'


def _snapshot():
    names = game_builds.IDENTITY_FILES + game_builds.RUNTIME_FILES['linux-x64']
    files = {name: {'sha256': '%064x' % i, 'size': 1} for i, name in enumerate(names, 1)}
    return {'version': VERSION, 'files': files, 'fingerprint': 'f' * 64, 'buildPlatform': 'linux-x64'}


class FakeRuns:
    """Stands in for qb._run: writes each stage's summary as the real stage would."""

    def __init__(self, *, d_rows=None, v2=None, official=None):
        self.d_rows = [{'ok': True}] * qb.D_V1_CASES if d_rows is None else d_rows
        self.v2 = {'ok': True, 'passedCases': 3, 'totalCases': 3} if v2 is None else v2
        self.official = {'ok': False, 'runs': [{'faults': ['independentObservationsDiffer']}] * 3} if official is None else official
        self.calls = []
        self.stores = []

    def __call__(self, cmd, log, store):
        script = Path(str(cmd[0])).name
        out = Path(str(cmd[cmd.index('--out') + 1]))
        out.mkdir(parents=True)
        self.calls.append(script)
        self.stores.append(store)
        if script == 'run_bounded_tick.py':
            data, code = {'runs': self.d_rows, 'ok': all(r['ok'] for r in self.d_rows)}, 0
        elif script == 'run_bounded_tick_v2.py':
            data, code = self.v2, 0 if self.v2.get('ok') else 1
        elif script == 'compare_ticks.py':
            data, code = self.official, 0 if self.official.get('ok') else 1
        else:
            raise AssertionError(script)
        (out / 'safe-summary.json').write_text(json.dumps(data))
        return code, 1.0


class TickStageTests(unittest.TestCase):
    def stages(self, fake):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(qb, '_run', fake):
            args = mock.Mock(snapshot='S', harmony_dll='H', worker='W')
            return qb.tick_stages(args, Path(tmp), Path(tmp) / 'candidate')

    def test_d_is_enabled_from_its_real_game_acceptance_not_from_the_official_comparison(self):
        fake = FakeRuns()
        v1, v2, rows = self.stages(fake)
        self.assertEqual((v1, v2), (True, True))
        self.assertEqual(fake.calls, ['run_bounded_tick.py', 'run_bounded_tick_v2.py', 'compare_ticks.py'])
        self.assertTrue(all(store is not None for store in fake.stores))
        self.assertEqual(rows['officialTickComparison']['agrees'], False)
        self.assertEqual(rows['officialTickComparison']['faults'], ['independentObservationsDiffer'])
        self.assertTrue(rows['officialTickComparison']['informationOnly'])
        self.assertEqual(rows['boundedTickV1'], {'ok': True, 'cases': 10, 'asExpected': 10, 'seconds': 1.0})

    def test_one_case_off_or_a_short_run_enables_nothing(self):
        for d_rows in ([{'ok': True}] * 9 + [{'ok': False}], [{'ok': True}] * 9, []):
            fake = FakeRuns(d_rows=d_rows)
            v1, v2, rows = self.stages(fake)
            self.assertEqual((v1, v2), (False, False))
            self.assertNotIn('run_bounded_tick_v2.py', fake.calls)
            self.assertNotIn('boundedTickV2', rows)

    def test_v2_needs_its_own_smoke(self):
        v1, v2, rows = self.stages(FakeRuns(v2={'ok': False, 'passedCases': 2, 'totalCases': 3}))
        self.assertEqual((v1, v2), (True, False))
        self.assertEqual(rows['boundedTickV2']['asExpected'], 2)

    def test_an_agreeing_official_comparison_still_grants_nothing_by_itself(self):
        v1, v2, _ = self.stages(FakeRuns(d_rows=[], official={'ok': True, 'runs': [{'faults': []}] * 3}))
        self.assertEqual((v1, v2), (False, False))


class MainTests(unittest.TestCase):
    def run_main(self, *, matrix=True, ab=True, map_ok=True, ticks=(True, True), extra=()):
        with tempfile.TemporaryDirectory() as tmp:
            out, store = Path(tmp) / 'out', Path(tmp) / 'store'
            seen = {}

            def ticks_stage(args, out_dir, candidate):
                trial = json.loads(next(candidate.iterdir()).read_text())
                seen['candidate'] = trial
                return ticks[0], ticks[1], {'boundedTickV1': {'ok': ticks[0]}}

            patches = [
                mock.patch.object(qb.validation_host, 'load_snapshot', return_value=_snapshot()),
                mock.patch.object(qb.validation_host, 'match_adapter', return_value=(None, None)),
                mock.patch.object(qb.validation_host, 'sha256_file', return_value='a' * 64),
                mock.patch.object(qb, 'matrix_stage', return_value=(matrix, {'cases': 1})),
                mock.patch.object(qb, 'official_ab_stage', return_value=(ab, {'cases': 1})),
                mock.patch.object(qb, 'map_stage', return_value=(map_ok, {'cases': 1})),
                mock.patch.object(qb, 'tick_stages', side_effect=ticks_stage),
                mock.patch.object(qb, '_source_state', return_value={'repositoryCommit': 'c', 'repositoryClean': True}),
            ]
            for p in patches:
                p.start()
            self.addCleanup(mock.patch.stopall)
            with mock.patch('sys.stdout'):
                code = qb.main(['--snapshot', tmp, '--harmony-dll', tmp, '--out', str(out), '--store', str(store), *extra])
            records = list(store.glob('*.json')) if store.exists() else []
            record = json.loads(records[0].read_text()) if records else None
            committed = out / 'committed-qualification.json'
            failed = out / 'qualification-failed.json'
            return code, record, (json.loads(committed.read_text()) if committed.exists() else None), failed.exists(), seen

    def test_everything_agreeing_grants_a_b_map_and_experimental_d(self):
        code, record, committed, failed, seen = self.run_main()
        self.assertEqual(code, 0)
        self.assertFalse(failed)
        row = record['qualified'][0]
        self.assertEqual((row['levels'], row['features']), (['A', 'B'], ['map']))
        self.assertEqual(record['experimentalFeatures'], ['bounded-tick.v1', 'bounded-tick.v2'])
        self.assertEqual(record['worker'], {'sha256': 'a' * 64})
        self.assertNotIn('worker', committed)
        self.assertEqual(game_builds.validate_record(committed)['buildId'], '1.7.6000-rev7')
        # The D stages run against a candidate that has exactly the levels and features already shown.
        self.assertEqual(seen['candidate']['qualified'][0]['features'], ['map'])

    def test_a_map_difference_keeps_a_b_but_not_map(self):
        code, record, _, _, seen = self.run_main(map_ok=False)
        self.assertEqual(code, 0)
        self.assertEqual(record['qualified'][0]['features'], [])
        self.assertEqual(record['qualified'][0]['featureEvidence'], {})
        self.assertEqual(seen['candidate']['qualified'][0]['features'], [])

    def test_skipped_map_is_not_granted(self):
        _, record, _, _, _ = self.run_main(extra=('--skip-map',))
        self.assertEqual(record['qualified'][0]['features'], [])

    def test_v2_without_v1_is_never_granted(self):
        _, record, _, _, _ = self.run_main(ticks=(False, False))
        self.assertEqual(record['experimentalFeatures'], [])
        _, record, _, _, _ = self.run_main(ticks=(True, False))
        self.assertEqual(record['experimentalFeatures'], ['bounded-tick.v1'])

    def test_a_matrix_or_a_b_difference_grants_nothing(self):
        for matrix, ab in ((False, True), (True, False)):
            code, record, committed, failed, seen = self.run_main(matrix=matrix, ab=ab)
            self.assertEqual(code, 1)
            self.assertIsNone(record)
            self.assertIsNone(committed)
            self.assertTrue(failed)
            self.assertNotIn('candidate', seen)


if __name__ == '__main__':
    unittest.main()
