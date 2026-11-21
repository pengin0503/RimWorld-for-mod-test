"""Per-build qualification records and automatic 1.7 build support (no game files needed)."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from test_validation_host import HOST_PLATFORM, Fixture, TempCase
from tools import game_builds as gb
from tools import validation_host as vh

REPO = Path(__file__).resolve().parents[1]
H = {name: hashlib.sha256(name.encode()).hexdigest() for name in
     (*gb.IDENTITY_FILES, 'libcoreclr.so', 'System.Private.CoreLib.dll', 'worker')}


def record(version='1.7.5014 rev1195', **changes):
    body = {
        'recordType': gb.RECORD_TYPE, 'schemaVersion': gb.SCHEMA_VERSION, 'gameVersion': version,
        'buildId': gb.build_id(version), 'method': 'automatic',
        'identitySha256': {name: H[name] for name in gb.IDENTITY_FILES},
        'experimentalFeatures': ['bounded-tick.v1'],
        'qualified': [{'platform': 'linux-x64', 'runtime': 'waylith', 'levels': ['A', 'B'], 'features': ['map'],
                       'runtimeSha256': {'libcoreclr.so': H['libcoreclr.so'],
                                         'System.Private.CoreLib.dll': H['System.Private.CoreLib.dll']},
                       'evidence': 'automatic', 'featureEvidence': {'map': 'automatic map'}}],
    }
    body.update(changes)
    return body


def manifest(hashes=None):
    return {name: {'sha256': digest} for name, digest in (hashes or H).items()}


class VersionTests(unittest.TestCase):
    def test_version_parsing_and_build_id(self):
        self.assertEqual(gb.parse_version('1.7.5014 rev1195\r\n'), (1, 7, 5014, 1195))
        self.assertEqual(gb.build_id('1.7.5014 rev1195'), '1.7.5014-rev1195')
        self.assertEqual(gb.game_version_numbers('1.7.5014 rev1195'), (1, 7, 5014))
        for bad in ('1.7', '1.7.5014', 'v1.7.5014 rev1', '1.7.5014 rev1 extra', '', None):
            with self.subTest(bad=bad):
                self.assertIsNone(gb.parse_version(bad))
        with self.assertRaises(ValueError):
            gb.build_id('unknown')

    def test_only_the_1_7_family_is_followed_automatically(self):
        self.assertEqual(gb.family('1.7.4985 rev1269')['id'], 'rimworld-1.7')
        self.assertEqual(gb.family('1.7.99999 rev1')['majorMinor'], '1.7')
        self.assertIsNone(gb.family('1.8.1 rev1'))
        self.assertIsNone(gb.family('1.6.4633 rev1261'))
        self.assertIsNone(gb.family('2.0.1 rev1'))
        self.assertIsNone(gb.family('garbage'))

    def test_unsupported_detail_says_why(self):
        self.assertIn('different major/minor', vh.unsupported_build_detail('1.8.1 rev1'))
        self.assertIn('not a RimWorld build version', vh.unsupported_build_detail('9.9'))
        self.assertIn('--allow-unknown-build', vh.unsupported_build_detail('1.8.1 rev1'))


class RecordTests(unittest.TestCase):
    def test_valid_record_is_normalized(self):
        normalized = gb.validate_record(record())
        self.assertEqual(normalized['qualified'][0]['levels'], ('A', 'B'))
        self.assertEqual(normalized['experimentalFeatures'], ('bounded-tick.v1',))

    def test_malformed_records_are_rejected(self):
        bad = {
            'unknown field': record(extra=1),
            'build id mismatch': record(buildId='1.7.5014-rev1'),
            'missing identity file': record(identitySha256={'Assembly-CSharp.dll': H['Assembly-CSharp.dll']}),
            'bad hash': record(identitySha256={name: 'x' for name in gb.IDENTITY_FILES}),
            'unknown level': record(qualified=[{**record()['qualified'][0], 'levels': ['Z']}]),
            'empty levels': record(qualified=[{**record()['qualified'][0], 'levels': []}]),
            'feature evidence without feature': record(qualified=[{**record()['qualified'][0], 'features': []}]),
            'wrong runtime files': record(qualified=[{**record()['qualified'][0], 'runtimeSha256': {'coreclr.dll': H['worker']}}]),
            'repeated platform': record(qualified=[record()['qualified'][0]] * 2),
            'unknown method': record(method='guess'),
            'bad worker': record(worker={'sha256': 'nope'}),
            'unknown experimental feature': record(experimentalFeatures=['bounded-tick.v9']),
        }
        for name, body in bad.items():
            with self.subTest(name=name), self.assertRaises(gb.RecordError):
                gb.validate_record(body)

    def test_the_committed_5014_record_qualifies_a_b_and_map(self):
        adapter = gb.committed_adapters(REPO / 'validation-data')['rimworld-1.7.5014-rev1195']
        self.assertEqual(adapter['version'], '1.7.5014 rev1195')
        self.assertEqual(adapter['record'], {'source': 'committed', 'method': 'automatic'})
        self.assertNotIn('worker', adapter)
        self.assertEqual(set(adapter['qualified']), {('linux-x64', 'waylith')})
        row = adapter['qualified'][('linux-x64', 'waylith')]
        # Map compared map for map with deterministic generation seeds (docs/research/2026-11-21-build-1.7.5014.md).
        self.assertEqual((row['levels'], row['features']), (('A', 'B'), ('map',)))
        self.assertEqual(adapter['experimentalFeatures'], ('bounded-tick.v1', 'bounded-tick.v2'))
        self.assertEqual(adapter['sha256']['Assembly-CSharp.dll'],
                         'aed36980a0a6a0469432d2cd062e0917102b0019d07afc832b2c959c362273bb')
        record = gb.read_record(REPO / 'validation-data/1.7.5014-rev1195' / gb.RECORD_NAME)
        self.assertEqual({k: record['comparison'][k]['ok'] for k in ('boundedTickV1', 'boundedTickV2')},
                         {'boundedTickV1': True, 'boundedTickV2': True})
        self.assertEqual(record['comparison']['officialAB']['notMatched'], [])
        self.assertTrue(record['comparison']['repositoryClean'])
        self.assertEqual(record['comparison']['map'] | {'seconds': None},
                         {'cases': 4, 'repeat': 5, 'judgement': 'sameMapEveryRun', 'equivalent': 4, 'notEquivalent': [],
                          'seconds': None})

    def test_the_committed_4985_record_is_the_former_adapter_unchanged(self):
        adapters = gb.committed_adapters(REPO / 'validation-data')
        self.assertEqual(set(adapters), {'rimworld-1.7.4985-rev1269', 'rimworld-1.7.5014-rev1195'})
        adapter = adapters['rimworld-1.7.4985-rev1269']
        former = {
            'version': '1.7.4985 rev1269',
            'experimentalFeatures': ('bounded-tick.v1', 'bounded-tick.v2'),
            'sha256': {
                'Assembly-CSharp.dll': '0be7a7ea4b3111d4430f45b36c234a5e43287880b0514b23915f2ef9a0629e16',
                'RimWorld.dll': '39bd67253a7fa5503ff7f2b51bc3ab5983fb1430acf57d7e8bb322d20e380555',
                'Waylith.dll': 'c69c2a2828c5594b58c9b28f0d19d5b25ff5cb16ceb46dc64f34dd59b7affc26',
                'UnityStubs.dll': 'ea962c9274514e0633d4e4c5471a1a98aff5fc52af20ca2e506c16dcd8be6f81',
                'Waylith.UnityCompat.dll': 'de9bcdb4399caac13435840b007994d054d4ffce9b0081ae5fcd3eb1479c10e0',
            },
            'qualified': {('linux-x64', 'waylith'): {
                'levels': ('A', 'B'),
                'runtimeSha256': {
                    'libcoreclr.so': 'eef17620f564c69d67ad9dcdef241902e9c12fef1cd090c973ab12a551f603d3',
                    'System.Private.CoreLib.dll': 'd2075bc8fd8e2f0b4780ec248034b30e33d4cdd72513730886c5989d1f8008b7',
                },
                'evidence': 'docs/research/test-host-qualification.md#linux-x64-waylithclr',
                'features': ('map',),
                'featureEvidence': {'map': 'docs/research/map-qualification.md'},
            }},
        }
        self.assertEqual({k: adapter[k] for k in former}, former)
        self.assertEqual(adapter['record'], {'source': 'committed', 'method': 'manual'})
        self.assertEqual(vh.ADAPTERS, adapters)

    def test_committed_records_must_match_their_folder_and_not_name_a_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / '1.7.1-rev1'
            folder.mkdir()
            (folder / gb.RECORD_NAME).write_text(json.dumps(record()), encoding='utf-8')
            with self.assertRaises(gb.RecordError):
                gb.committed_adapters(tmp)
            folder.rename(Path(tmp) / '1.7.5014-rev1195')
            (Path(tmp) / '1.7.5014-rev1195' / gb.RECORD_NAME).write_text(
                json.dumps(record(worker={'sha256': H['worker']})), encoding='utf-8')
            with self.assertRaises(gb.RecordError):
                gb.committed_adapters(tmp)
            (Path(tmp) / '1.7.5014-rev1195' / gb.RECORD_NAME).write_text(json.dumps(record()), encoding='utf-8')
            self.assertIn('rimworld-1.7.5014-rev1195', gb.committed_adapters(tmp))


class ResolveAdapterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Path(temp.name)

    def write(self, body, name='r.json'):
        (self.store / name).write_text(json.dumps(body), encoding='utf-8')

    def test_registered_record_wins(self):
        adapters = {'rimworld-1.7.5014-rev1195': gb.adapter_from_record(gb.validate_record(record()), source='committed')}
        name, adapter, notes = vh.resolve_adapter(manifest(), '1.7.5014 rev1195', adapters, store=str(self.store))
        self.assertEqual((name, adapter['record']['source'], notes), ('rimworld-1.7.5014-rev1195', 'committed', []))

    def test_new_1_7_build_without_record_runs_experimental(self):
        name, adapter, notes = vh.resolve_adapter(manifest(), '1.7.6000 rev1', {}, store=str(self.store))
        self.assertEqual(name, 'rimworld-1.7.6000-rev1')
        self.assertEqual((adapter['family'], adapter['qualified'], adapter['record']), ('rimworld-1.7', {}, None))
        self.assertEqual(notes, [])
        self.assertEqual(vh.match_adapter(manifest(), {name: adapter}), (None, None))

    def test_other_major_minor_has_no_adapter(self):
        self.assertEqual(vh.resolve_adapter(manifest(), '1.8.1 rev1', {}, store='')[:2], (None, None))

    def test_private_record_applies_only_to_its_files_and_worker(self):
        self.write(record(worker={'sha256': H['worker']}))
        name, adapter, notes = vh.resolve_adapter(manifest(), '1.7.5014 rev1195', {}, store=str(self.store),
                                                  worker_sha256=H['worker'])
        self.assertEqual(adapter['record'], {'source': 'private', 'method': 'automatic', 'file': 'r.json'})
        self.assertEqual(adapter['qualified'][('linux-x64', 'waylith')]['levels'], ('A', 'B'))
        self.assertEqual(notes, [])
        # Another Worker build: not used, and the result says why.
        _, adapter, notes = vh.resolve_adapter(manifest(), '1.7.5014 rev1195', {}, store=str(self.store),
                                               worker_sha256='0' * 64)
        self.assertEqual(adapter['qualified'], {})
        self.assertIn('another Worker build', notes[0])
        # Other file hashes or another version: silently not applicable.
        changed = dict(H, **{'Assembly-CSharp.dll': '1' * 64})
        self.assertEqual(vh.resolve_adapter(manifest(changed), '1.7.5014 rev1195', {}, store=str(self.store),
                                            worker_sha256=H['worker'])[1]['qualified'], {})
        self.assertEqual(vh.resolve_adapter(manifest(), '1.7.5015 rev1', {}, store=str(self.store),
                                            worker_sha256=H['worker'])[1]['qualified'], {})

    def test_malformed_private_record_is_reported_not_used(self):
        self.write({'recordType': gb.RECORD_TYPE}, 'broken.json')
        _, adapter, notes = vh.resolve_adapter(manifest(), '1.7.5014 rev1195', {}, store=str(self.store))
        self.assertEqual(adapter['qualified'], {})
        self.assertTrue(notes and notes[0].startswith('qualification store: broken.json'))

    def test_store_from_environment_and_empty_string_disables_it(self):
        self.write(record(worker={'sha256': H['worker']}))
        with mock.patch.dict('os.environ', {gb.STORE_ENV: str(self.store)}):
            self.assertTrue(vh.resolve_adapter(manifest(), '1.7.5014 rev1195', {}, worker_sha256=H['worker'])[1]['qualified'])
            self.assertFalse(vh.resolve_adapter(manifest(), '1.7.5014 rev1195', {}, store='',
                                                worker_sha256=H['worker'])[1]['qualified'])

    def test_known_version_with_other_files_is_noted(self):
        adapters = {'rimworld-1.7.5014-rev1195': gb.adapter_from_record(gb.validate_record(record()), source='committed')}
        changed = dict(H, **{'RimWorld.dll': '2' * 64})
        _, adapter, notes = vh.resolve_adapter(manifest(changed), '1.7.5014 rev1195', adapters, store='')
        self.assertEqual(adapter['qualified'], {})
        self.assertIn('file hashes differ', notes[0])


class ControllerFollowsNewBuildTests(TempCase):
    """An unregistered 1.7 build runs at once (experimental); a matching record qualifies it."""
    fixture_platform = HOST_PLATFORM

    def setUp(self):
        super().setUp()
        (self.fx.game / 'Version.txt').write_text('1.7.6000 rev7\r\n', encoding='utf-8')
        self.info = self.fx.prepare()
        self.fx.mod('target')
        self.worker_sha = hashlib.sha256(b'fake worker assembly').hexdigest()

    def run_with(self, store, out):
        return vh.run_validation(self.fx.snapshot, self.fx.request(['*target']), self.root / out, self.fx.worker,
                                 adapters={}, platform=HOST_PLATFORM, qualification_store=store)

    def private_record(self, worker):
        files = self.info['files']
        body = record('1.7.6000 rev7', worker={'sha256': worker})
        body['identitySha256'] = {name: files[name]['sha256'] for name in gb.IDENTITY_FILES}
        runtime = gb.RUNTIME_FILES[self.fx.platform]
        body['qualified'] = [{'platform': self.fx.platform, 'runtime': 'waylith', 'levels': ['A', 'B'],
                              'runtimeSha256': {name: files[name]['sha256'] for name in runtime},
                              'evidence': 'automatic test'}]
        return body

    def test_unregistered_1_7_build_is_experimental_not_blocked(self):
        self.assertEqual(self.info['adapter'], 'rimworld-1.7.6000-rev7')
        result = self.run_with('', 'out-plain')
        self.assertNotEqual(result['status'], 'blocked')
        self.assertEqual(result['fidelity'], 'experimental')
        self.assertEqual((result['game']['adapter'], result['game']['family'], result['game']['qualificationRecord']),
                         ('rimworld-1.7.6000-rev7', 'rimworld-1.7', None))
        self.assertIn('experimental', [r['code'] for r in result['reasons']])

    def test_matching_private_record_qualifies_and_another_worker_does_not(self):
        store = self.root / 'store'
        store.mkdir()
        (store / 'good.json').write_text(json.dumps(self.private_record(self.worker_sha)), encoding='utf-8')
        result = self.run_with(str(store), 'out-qualified')
        self.assertEqual((result['status'], result['fidelity']), ('passed', 'qualified'))
        self.assertEqual(result['game']['qualificationRecord'], {'source': 'private', 'method': 'automatic', 'file': 'good.json'})
        (store / 'good.json').write_text(json.dumps(self.private_record('0' * 64)), encoding='utf-8')
        result = self.run_with(str(store), 'out-other-worker')
        self.assertEqual(result['fidelity'], 'experimental')
        self.assertIn('another Worker build', result['game']['qualificationNotes'][0])

    def test_other_major_minor_blocks_with_reason(self):
        (self.root / 'v18').mkdir()
        fx = Fixture(self.root / 'v18', self.fx.platform)
        (fx.game / 'Version.txt').write_text('1.8.100 rev1\n', encoding='utf-8')
        fx.prepare()
        fx.mod('target')
        result = vh.run_validation(fx.snapshot, fx.request(['*target']), self.root / 'out-18', fx.worker,
                                   adapters={}, platform=HOST_PLATFORM, qualification_store='')
        self.assertEqual((result['status'], result['reasons'][0]['code']), ('blocked', 'unknownBuild'))
        self.assertIn('different major/minor', result['reasons'][0]['detail'])


if __name__ == '__main__':
    unittest.main()
