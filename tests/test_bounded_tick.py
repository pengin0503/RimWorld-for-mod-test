"""D must reject forged reachability and preserve incomplete observations."""
import copy
from pathlib import Path
import unittest
from tools import validation_host as vh


def request():
    return {'recordType': 'modValidationRequest', 'schemaVersion': 1, 'levels': ['A', 'D'],
            'mods': [{'path': 'probe'}, {'path': 'target', 'target': True}], 'map': {'seed': 'RWMT-tick'},
            'tests': ['bounded-tick.v1'], 'tick': {'count': 600, 'observeAt': [0, 60, 600]},
            'expectations': {'tickObservations': [{'tick': 600, 'id': 'fixture.counter', 'equals': 600}]}}


def evidence():
    return {'caseId': 'bounded-tick.v1', 'observerVersion': 1, 'status': 'completed',
            'startTick': 1000, 'endTick': 1600, 'advanced': 600,
            'initialization': 'gameFinalizeInitAndStartedNewGame',
            'observations': [{'tick': n, 'gameTick': 1000+n, 'values': {'fixture.counter': n}}
                             for n in (0, 60, 600)]}


class TickRequestTests(unittest.TestCase):
    def test_fixed_case_is_accepted_and_normalized(self):
        r = vh.validate_request(request(), Path('/tmp'))
        self.assertEqual(r['tick'], {'count': 600, 'observeAt': [0, 60, 600]})

    def test_bad_tick_requests_are_rejected(self):
        variants = []
        for count in (0, 60001, True, 1.5, '600'):
            r = request(); r['tick']['count'] = count; variants.append(r)
        for points in ([], [60, 0, 600], [0, 60, 60, 600], [0, 60], [0, 601], [False, 600], list(range(65))):
            r = request(); r['tick']['observeAt'] = points; variants.append(r)
        for patch in ({'map': None}, {'levels': ['A', 'C', 'D']}, {'levels': ['A', 'B', 'D']},
                      {'tests': []}, {'tick': None}, {'levels': ['A']},
                      {'expectations': {'tickObservations': []}},
                      {'expectations': {'tickObservations': [{'tick': 59, 'id': 'fixture.counter', 'equals': 59}]}},
                      {'expectations': {'tickObservations': [{'tick': 600, 'id': 'fixture.counter', 'equals': True}]}}):
            variants.append(dict(request(), **patch))
        for r in variants:
            with self.subTest(r=r), self.assertRaises(vh.RequestError):
                vh.validate_request(r, Path('/tmp'))

    def test_unknown_id_is_well_formed_but_not_a_pass(self):
        r = request(); r['expectations']['tickObservations'][0]['id'] = 'unknown.counter'
        normalized = vh.validate_request(r, Path('/tmp'))
        stage, inc, failed = vh.evaluate_tick(normalized, evidence())
        self.assertEqual(stage['status'], 'incomplete')
        self.assertFalse(failed)


class TickEvidenceTests(unittest.TestCase):
    def evaluate(self, e):
        return vh.evaluate_tick(vh.validate_request(request(), Path('/tmp')), e)

    def test_complete_is_experimental_and_mismatch_is_stage_failure(self):
        stage, inc, failed = self.evaluate(evidence())
        self.assertEqual(stage['status'], 'completed')
        self.assertEqual(stage['fidelity'], 'experimental')
        self.assertIn('dNotQualified', [x['code'] for x in inc])
        self.assertFalse(failed)
        e = evidence(); e['observations'][-1]['values']['fixture.counter'] = 599
        stage, _, failed = self.evaluate(e)
        self.assertEqual(stage['status'], 'failed')
        self.assertEqual(failed[0]['code'], 'tickObservationMismatch')

    def test_missing_forged_or_partial_evidence_never_completes(self):
        variants = [None, {}, dict(evidence(), advanced=601), dict(evidence(), endTick=1601),
                    dict(evidence(), startTick=True), dict(evidence(), status='incomplete'),
                    dict(evidence(), initialization='mapOnly'), dict(evidence(), observerVersion=0)]
        for mutate in (lambda x: x['observations'].pop(0),
                       lambda x: x['observations'].append(copy.deepcopy(x['observations'][-1])),
                       lambda x: x['observations'][1].update(gameTick=1061),
                       lambda x: x['observations'][1].update(values={}),
                       lambda x: x['observations'][0].update(tick=False)):
            e = evidence(); mutate(e); variants.append(e)
        for e in variants:
            with self.subTest(e=e):
                stage, inc, failed = self.evaluate(e)
                self.assertEqual(stage['status'], 'incomplete')
                self.assertFalse(failed)
                self.assertIn('tickObservationIncomplete', [x['code'] for x in inc])


class TickControllerTests(unittest.TestCase):
    def test_unsupported_platform_blocks_before_game_access(self):
        import json, tempfile
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); path = root / 'request.json'; path.write_text(json.dumps(request()))
            r = vh.run_validation(root / 'absent', path, root / 'out', root / 'absent', platform='windows-x64')
            self.assertEqual(r['status'], 'blocked')
            self.assertEqual(r['reasons'][0]['code'], 'boundedTickUnsupported')

    @unittest.skipUnless(__import__('sys').platform.startswith('linux'), 'Linux D contract only')
    def test_cache_separates_d_configuration_and_rejects_partial_baseline(self):
        import json, tempfile, textwrap
        from tests.test_validation_host import Fixture, FAKE_WORKER
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); fx = Fixture(root)
            fx.mod('probe'); fx.mod('target'); fx.prepare()
            # Controller contract double only, not game tick qualification.
            fx.adapters['fake-9.9.1']['experimentalFeatures'] = ['bounded-tick.v1']
            script = FAKE_WORKER.replace("with open(request['resultPath'], 'w', encoding='utf-8') as stream:", textwrap.dedent("""
    if request.get('tick'):
        count = request['tick']['count']
        result['tick'] = {'caseId': 'bounded-tick.v1', 'observerVersion': 1, 'status': 'completed',
            'initialization': 'gameFinalizeInitAndStartedNewGame', 'startTick': 1000,
            'endTick': 1000 + count, 'advanced': count,
            'observations': [{'tick': t, 'gameTick': 1000+t, 'values': {'fixture.counter': t}}
                             for t in request['tick']['observeAt']]}
    with open(request['resultPath'], 'w', encoding='utf-8') as stream:"""))
            (fx.worker / vh.WORKER_NAME).write_text(script)
            fields = request(); fields.pop('mods'); cache = root / 'cache'
            def run(**updates):
                return fx.run(['probe', '*target'], baseline_cache=cache, **dict(fields, **updates))[0]
            first = run()
            self.assertEqual(first['stages']['D']['status'], 'completed')
            self.assertEqual(first['status'], 'incomplete')
            self.assertFalse(first['diagnostics']['baselineCached'])
            self.assertTrue(run()['diagnostics']['baselineCached'])
            shorter = run(tick={'count': 60, 'observeAt': [0, 60]},
                          expectations={'tickObservations': [{'tick': 60, 'id': 'fixture.counter', 'equals': 60}]})
            self.assertFalse(shorter['diagnostics']['baselineCached'])
            self.assertFalse(run(tick={'count': 600, 'observeAt': [0, 600]})['diagnostics']['baselineCached'])
            self.assertFalse(run(expectations={'tickObservations': [
                {'tick': 600, 'id': 'fixture.counter', 'equals': 599}]})['diagnostics']['baselineCached'])
            # A prior partial or old-version result must be executed again, not trusted.
            for path in cache.glob('*.json'):
                if path.name.endswith('map-observation.json'): continue
                row = json.loads(path.read_text()); row['worker']['tick']['status'] = 'incomplete'
                path.write_text(json.dumps(row))
            self.assertFalse(run()['diagnostics']['baselineCached'])


class TickCheckpointTests(unittest.TestCase):
    def test_partial_checkpoint_requires_run_identity_and_never_completes(self):
        import json, tempfile
        from tools import bounded_tick
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'tick-evidence.json'
            data = {'recordType': 'rwmtTickCheckpoint', 'schemaVersion': 1, 'runId': 'run', 'nonce': 'secret',
                    'tick': evidence()}
            path.write_text(json.dumps(data))
            self.assertIsNone(bounded_tick.load_checkpoint(Path(temp), 'run', 'other'))
            got = bounded_tick.load_checkpoint(Path(temp), 'run', 'secret')
            self.assertEqual(got['status'], 'incomplete')
            self.assertEqual(got['observations'][-1]['tick'], 600)
            stage, _, _ = vh.evaluate_tick(vh.validate_request(request(), Path('/tmp')), got)
            self.assertEqual(stage['status'], 'incomplete')
            path.write_text('invalid')
            self.assertIsNone(bounded_tick.load_checkpoint(Path(temp), 'run', 'secret'))
