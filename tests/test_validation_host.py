"""Game-free tests of the validation Controller.

A synthetic snapshot and a fake Worker (a small Python script that honours the
Worker request/result contract) stand in for the user's private game files, so
these tests run in public CI. Real-game behaviour is covered by the private
tests/integration/run_fixture_matrix.py.
"""
from pathlib import Path
import hashlib
import json
import os
import stat
import sys
import tempfile
import textwrap
import time
import unittest

from tools import validation_host as vh

LINUX = sys.platform.startswith('linux')

FAKE_WORKER = textwrap.dedent('''\
    #!/usr/bin/env python3
    # Fake Worker for Controller tests. Behaviour is chosen by mod folder names.
    import json, os, subprocess, sys, time
    request = json.load(open(sys.argv[2], encoding='utf-8'))
    mods = sorted(os.listdir(os.path.join(request['hostDir'], 'Mods')))
    def event(level, message, stream):
        stream.write(json.dumps({'seq': 1, 't': 0.1, 'level': level, 'category': 'Verse', 'stage': 'loadPlayData',
                                 'thread': 'main', 'message': message, 'truncated': False}) + '\\n')
    if 'hang' in mods:
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])
        with open(os.path.join(os.path.dirname(request['resultPath']), 'child.pid'), 'w') as stream:
            stream.write(str(child.pid))
        time.sleep(600)
    if 'memory' in mods:
        block = bytearray(700 * 1024 * 1024)
        for i in range(0, len(block), 4096):
            block[i] = 1
        time.sleep(600)
    if 'noisy' in mods:
        sys.stdout.write('x' * (2 * 1024 * 1024))
        sys.stdout.flush()
        time.sleep(600)
    with open(request['eventsPath'], 'w', encoding='utf-8') as stream:
        event('warning', 'present in every run', stream)
        if 'bad' in mods:
            event('error', 'Could not resolve cross-reference to RWMT_Missing', stream)
    expectations = request['expectations']
    defs = [{'expected': d, 'actualExists': d['exists'], 'outcome': 'match'} for d in expectations.get('defs', [])]
    patches = [{'expected': p, 'outcome': 'missing' if 'nopatch' in mods else 'match'}
               for p in expectations.get('harmonyPatches', [])]
    order = request['expectedModOrder']
    actual = order[:-1] if 'reorder' in mods else order
    result = {
        'recordType': 'rwmtWorkerResult', 'schemaVersion': 1, 'runId': request['runId'],
        'nonce': 'wrong' if 'stale' in mods else request['nonce'], 'executionStatus': 'completed', 'failure': None,
        'runtime': {'frameworkDescription': 'fake'}, 'stages': [], 'skippedOfficialSteps': [], 'deviations': [],
        'playDataLoaded': True, 'verseLogLimitReached': False,
        'activeLanguage': request['language'],
        'runningMods': [], 'modClasses': [],
        'modOrder': {'matches': actual == order, 'expected': order, 'actual': actual},
        'checks': {'defs': defs, 'defValues': [], 'keyed': [],
                   'harmony': {'assemblies': [], 'available': True, 'expected': patches, 'unexpected': []}},
        'diagnosticsSummary': {'written': 2, 'dropped': 0, 'truncated': 0, 'byLevel': {}},
    }
    with open(request['resultPath'], 'w', encoding='utf-8') as stream:
        json.dump(result, stream)
''')


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Fixture:
    """A synthetic game folder, snapshot, fake Worker and mods in a temporary directory."""

    def __init__(self, root):
        self.root = root
        self.game = root / 'game-source'
        for name in vh.REQUIRED_GAME_FILES:
            path = self.game / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f'fake {name}'.encode())
        (self.game / 'Version.txt').write_text('9.9.1 rev1\n', encoding='utf-8')
        (self.game / 'RimWorld').write_bytes(b'official executable - must never be linked or run')
        (self.game / 'Other.dll').write_bytes(b'other')
        self.about(self.game / 'Data' / 'Core', 'Ludeon.RimWorld')
        self.about(self.game / 'Data' / 'Royalty', 'Ludeon.RimWorld.Royalty')
        languages = self.game / 'Data' / 'Core' / 'Languages'
        (languages / 'English').mkdir(parents=True)
        (languages / 'Japanese (日本語).tar').write_bytes(b'tar')
        target = '.NETCoreApp,Version=v10.0/linux-x64'
        (self.game / 'RimWorld.deps.json').write_text(json.dumps({
            'runtimeTarget': {'name': target},
            'targets': {target: {'RimWorld/1.0.0': {'runtime': {'RimWorld.dll': {}}},
                                 'runtimepack.Fake/1.0': {'runtime': {'System.Private.CoreLib.dll': {}},
                                                          'native': {'libcoreclr.so': {}}}}},
            'libraries': {'RimWorld/1.0.0': {'type': 'project'}, 'runtimepack.Fake/1.0': {'type': 'runtimepack'}},
        }), encoding='utf-8')
        (self.game / 'RimWorld.runtimeconfig.json').write_text(json.dumps({'runtimeOptions': {
            'tfm': 'net10.0', 'includedFrameworks': [{'name': 'Microsoft.NETCore.App', 'version': '10.0.13-waylithclr.dev'}],
            'configProperties': {'WaylithClr.LaxCallvirt': True, 'System.Foo': False}}}), encoding='utf-8')
        self.snapshot = root / 'snapshot'
        self.adapters = {'fake-9.9.1': {
            'version': '9.9.1 rev1',
            'sha256': {'Assembly-CSharp.dll': sha(b'fake Assembly-CSharp.dll')},
            'qualified': {('linux-x64', 'waylith'): {'levels': ('A', 'B'), 'runtimeSha256': {}, 'evidence': 'test'}},
        }}
        self.worker = root / 'worker'
        self.worker.mkdir()
        script = self.worker / vh.WORKER_NAME
        script.write_text(FAKE_WORKER, encoding='utf-8')
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
        (self.worker / f'{vh.WORKER_NAME}.dll').write_bytes(b'fake worker assembly')
        self.mods = root / 'mods'
        self.count = 0

    @staticmethod
    def about(folder, package_id):
        (folder / 'About').mkdir(parents=True, exist_ok=True)
        (folder / 'About' / 'About.xml').write_text(
            f'<ModMetaData><packageId>{package_id}</packageId></ModMetaData>', encoding='utf-8')

    def mod(self, folder, package_id=None, harmony=False):
        path = self.mods / folder
        self.about(path, package_id or f'test.{folder}')
        (path / 'Defs').mkdir(exist_ok=True)
        (path / 'Defs' / 'a.xml').write_text('<Defs/>', encoding='utf-8')
        if harmony:
            (path / 'Assemblies').mkdir(exist_ok=True)
            (path / 'Assemblies' / '0Harmony.dll').write_bytes(b'not loaded by fake worker')
        return path

    def prepare(self):
        return vh.prepare_game(self.game, self.snapshot, log=lambda *_: None)

    def request(self, mods, **fields):
        self.count += 1
        body = {'recordType': 'modValidationRequest', 'schemaVersion': 1, 'levels': ['A'],
                'mods': [{'path': str(self.mods / name.lstrip('*')), 'target': name.startswith('*')} for name in mods]}
        body.update(fields)
        path = self.root / f'request-{self.count}.json'
        path.write_text(json.dumps(body, ensure_ascii=False), encoding='utf-8')
        return path

    def run(self, mods, *, platform='linux-x64', **kwargs):
        options = {k: kwargs.pop(k) for k in ('runtime', 'baseline_cache', 'allow_unknown_build', 'keep_run_dirs')
                   if k in kwargs}
        out = self.root / f'out-{self.count + 1}'
        request = self.request(mods, **kwargs)
        return vh.run_validation(self.snapshot, request, out, self.worker, adapters=self.adapters, platform=platform,
                                 **options), out


class TempCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.addCleanup(self.make_writable)
        self.fx = Fixture(self.root)

    def make_writable(self):
        for current, dirs, files in os.walk(self.root):
            os.chmod(current, 0o755)
            for name in files:
                path = Path(current) / name
                if not path.is_symlink():
                    path.chmod(0o644)


class RequestTests(TempCase):
    def load(self, **fields):
        self.fx.mod('one')
        return vh.load_request(self.fx.request(['*one'], **fields))

    def test_minimal_request_gets_defaults_and_absolute_paths(self):
        request = self.load()
        self.assertEqual(request['official'], ['Core'])
        self.assertEqual(request['language'], 'English')
        self.assertEqual(request['limits'], vh.DEFAULT_LIMITS)
        self.assertTrue(Path(request['mods'][0]['path']).is_absolute())
        self.assertEqual(len(request['sha256']), 64)

    def test_invalid_requests_are_rejected(self):
        cases = {
            'unknown field': {'extra': 1},
            'no A': {'levels': ['B']},
            'unknown level': {'levels': ['A', 'D']},
            'core not first': {'official': ['Royalty', 'Core']},
            'patch without B': {'expectations': {'harmonyPatches': [
                {'owner': 'o', 'targetAssembly': 'a', 'targetType': 't', 'targetMethod': 'm', 'targetParameters': [],
                 'kind': 'postfix', 'patchType': 'p', 'patchMethod': 'q'}]}},
            'bad patch kind': {'levels': ['A', 'B'], 'expectations': {'harmonyPatches': [
                {'owner': 'o', 'targetAssembly': 'a', 'targetType': 't', 'targetMethod': 'm', 'targetParameters': [],
                 'kind': 'replace', 'patchType': 'p', 'patchMethod': 'q'}]}},
            'incomplete def check': {'expectations': {'defs': [{'type': 'ThingDef', 'defName': 'X'}]}},
            'limit too small': {'limits': {'timeoutSeconds': 1}},
            'unknown limit': {'limits': {'ticks': 10}},
            'language path': {'language': '../English'},
            'tests without C': {'tests': ['x']},
            'schema': {'schemaVersion': 2},
        }
        for name, fields in cases.items():
            with self.subTest(name):
                with self.assertRaises(vh.RequestError):
                    self.load(**fields)

    def test_a_target_mod_is_required(self):
        self.fx.mod('one')
        with self.assertRaises(vh.RequestError):
            vh.load_request(self.fx.request(['one']))


class SnapshotTests(TempCase):
    def test_snapshot_is_read_only_copy_with_manifest_and_adapter(self):
        info = self.fx.prepare()
        game = self.fx.snapshot / 'game'
        self.assertEqual(info['officialContent'], ['Core', 'Royalty'])
        self.assertEqual(info['files']['Other.dll']['sha256'], sha(b'other'))
        self.assertIsNone(info['adapter'])
        self.assertEqual(vh.match_adapter(info['files'], self.fx.adapters)[0], 'fake-9.9.1')
        self.assertFalse(os.stat(game / 'Other.dll').st_mode & stat.S_IWUSR)
        if LINUX and os.geteuid() != 0:
            with self.assertRaises(PermissionError):
                (game / 'Other.dll').write_bytes(b'x')

    def test_missing_required_file_blocks(self):
        (self.fx.game / 'Assets.zip').unlink()
        with self.assertRaises(vh.Blocked) as caught:
            self.fx.prepare()
        self.assertEqual(caught.exception.code, 'missingGameFiles')

    def test_existing_snapshot_is_never_overwritten(self):
        self.fx.snapshot.mkdir()
        with self.assertRaises(vh.Blocked):
            self.fx.prepare()

    def test_modified_snapshot_is_detected(self):
        self.fx.prepare()
        game = self.fx.snapshot / 'game'
        vh.load_snapshot(self.fx.snapshot)
        for name, change in [('size', lambda p: p.write_bytes(b'longer content')),
                             ('identity', lambda p: p.write_bytes(b'fake Assembly-CSharp.dlX'))]:
            with self.subTest(name):
                target = game / ('Other.dll' if name == 'size' else 'Assembly-CSharp.dll')
                original = target.read_bytes()
                target.chmod(0o644)
                change(target)
                with self.assertRaises(vh.Blocked) as caught:
                    vh.load_snapshot(self.fx.snapshot)
                self.assertEqual(caught.exception.code, 'snapshotModified')
                target.write_bytes(original)

    def test_extra_file_in_selected_official_content_is_detected(self):
        self.fx.prepare()
        core = self.fx.snapshot / 'game' / 'Data' / 'Core'
        core.chmod(0o755)
        (core / 'Planted.xml').write_text('<Defs/>', encoding='utf-8')
        with self.assertRaises(vh.Blocked):
            vh.load_snapshot(self.fx.snapshot, official=['Core'])
        vh.load_snapshot(self.fx.snapshot, official=['Royalty'])

    def test_language_resolution(self):
        game = self.fx.game
        self.assertEqual(vh.resolve_language(game, 'English'), 'English')
        self.assertEqual(vh.resolve_language(game, 'Japanese'), 'Japanese (日本語)')
        self.assertEqual(vh.resolve_language(game, 'Japanese (日本語)'), 'Japanese (日本語)')
        with self.assertRaises(vh.Blocked):
            vh.resolve_language(game, 'Klingon')


def worker_result(**changes):
    result = {
        'executionStatus': 'completed', 'playDataLoaded': True, 'verseLogLimitReached': False,
        'activeLanguage': 'English', 'modOrder': {'matches': True, 'expected': [], 'actual': []},
        'checks': {'defs': [{'outcome': 'match'}], 'defValues': [], 'keyed': [],
                   'harmony': {'expected': [{'outcome': 'match'}], 'unexpected': []}},
        'diagnosticsSummary': {'dropped': 0},
    }
    result.update(changes)
    return result


class EvaluationTests(unittest.TestCase):
    request = {'levels': ['A', 'B'], 'language': 'English',
               'expectations': {'harmonyPatches': [{'owner': 'x'}], 'defs': [], 'defValues': [], 'keyed': []}}
    mods = [{'packageId': 'test.target', 'folderName': 'Target', 'target': True}]
    warning = {'level': 'warning', 'category': 'Verse', 'message': 'present in every run'}
    error = {'level': 'error', 'category': 'Verse', 'message': 'Could not resolve cross-reference (test.target)'}

    def evaluate(self, worker='default', *, events=(), problem=None, process=None, fidelity='qualified', request=None,
                 baseline_problem=None):
        return vh.evaluate(request or self.request, self.mods, worker_result() if worker == 'default' else worker, problem,
                           list(events), worker_result(), baseline_problem, [self.warning], process or {}, fidelity)

    def codes(self, outcome):
        return [r['code'] for r in outcome[2]]

    def test_clean_qualified_run_passes(self):
        status, execution, reasons, stages, fresh = self.evaluate(events=[self.warning])
        self.assertEqual((status, execution, reasons, fresh), ('passed', 'completed', [], []))
        self.assertEqual((stages['A']['status'], stages['B']['status'], stages['C']['status']),
                         ('completed', 'completed', 'notRequested'))

    def test_status_table(self):
        warning, error, request = self.warning, self.error, self.request
        cases = [
            ('experimental never passes', {'fidelity': 'experimental'}, 'incomplete', ['experimental']),
            ('expectation mismatch', {'worker': worker_result(checks={'defs': [{'outcome': 'mismatch'}],
                                      'harmony': {'expected': [{'outcome': 'match'}]}})}, 'failed', ['expectationMismatch']),
            ('mismatch plus timeout stays incomplete',
             {'worker': worker_result(executionStatus='interrupted', failure='deadline'), 'process': {'killedFor': 'timeout'}},
             'incomplete', ['timeout', 'workerInterrupted']),
            ('harmony patch missing', {'worker': worker_result(checks={'defs': [], 'harmony': {'expected': [{'outcome': 'missing'}]}})},
             'failed', ['harmonyPatchMissing']),
            ('harmony check error', {'worker': worker_result(checks={'defs': [], 'harmony': {'expected': [{'outcome': 'error'}]}})},
             'incomplete', ['harmonyCheckError']),
            ('new error', {'events': [error, warning]}, 'failed', ['newErrors']),
            ('new warning', {'events': [warning, warning]}, 'failed', ['newWarnings']),
            ('new error with experimental runtime', {'events': [error], 'fidelity': 'experimental'}, 'incomplete',
             ['experimental', 'newErrors']),
            ('mod order changed', {'worker': worker_result(modOrder={'matches': False, 'expected': ['a'], 'actual': []})},
             'incomplete', ['modOrderMismatch']),
            ('diagnostics dropped', {'worker': worker_result(diagnosticsSummary={'dropped': 3})}, 'incomplete', ['diagnosticsDropped']),
            ('verse log limit', {'worker': worker_result(verseLogLimitReached=True)}, 'incomplete', ['verseLogLimit']),
            ('language fallback', {'worker': worker_result(activeLanguage='English (fallback)')}, 'incomplete', ['languageNotApplied']),
            ('missing result', {'worker': None, 'problem': 'workerResultMissing'}, 'incomplete', ['workerResultMissing']),
            ('stale result', {'worker': None, 'problem': 'workerResultStale'}, 'incomplete', ['workerResultStale']),
            ('baseline did not finish', {'baseline_problem': 'baseline timed out'}, 'incomplete', ['baselineIncomplete']),
            ('load exception', {'worker': worker_result(loadException='System.Exception: boom\n at x')}, 'failed', ['loadException']),
            ('B without expected patches',
             {'request': dict(request, expectations=dict(request['expectations'], harmonyPatches=[]))},
             'incomplete', ['noExpectedPatches']),
            ('check could not be evaluated', {'worker': worker_result(checks={'defs': [{'outcome': 'error'}],
                                              'harmony': {'expected': [{'outcome': 'match'}]}})}, 'incomplete', ['checkError']),
        ]
        for name, kwargs, status, codes in cases:
            with self.subTest(name):
                outcome = self.evaluate(**kwargs)
                self.assertEqual(outcome[0], status, outcome[2])
                for code in codes:
                    self.assertIn(code, self.codes(outcome))

    def test_unrequested_level_b_is_reported_as_not_requested(self):
        request = dict(self.request, levels=['A'], expectations=dict(self.request['expectations'], harmonyPatches=[]))
        status, _, reasons, stages, _ = self.evaluate(request=request)
        self.assertEqual((status, reasons, stages['B']['status']), ('passed', [], 'notRequested'))

    def test_new_diagnostics_is_a_multiset_difference_and_names_targets(self):
        outcome = self.evaluate(events=[self.warning, self.error, self.error])
        self.assertEqual(len(outcome[4]), 2)
        self.assertEqual(outcome[4][0]['mentionsTargets'], ['test.target'])
        self.assertEqual(vh.new_diagnostics([self.warning, self.warning], [self.warning]), [self.warning])


@unittest.skipUnless(LINUX, 'running the Worker is implemented for Linux only')
class RunTests(TempCase):
    def setUp(self):
        super().setUp()
        self.fx.prepare()

    def test_clean_target_passes_and_never_links_the_official_executable(self):
        self.fx.mod('dep')
        self.fx.mod('target')
        result, out = self.fx.run(['dep', '*target'], keep_run_dirs=True,
                                  expectations={'defs': [{'type': 'ThingDef', 'defName': 'X', 'exists': True}]})
        self.assertEqual(result['status'], 'passed', result.get('reasons'))
        self.assertEqual(result['fidelity'], 'qualified')
        host = out / 'target' / 'host'
        self.assertFalse((host / 'RimWorld').exists())
        self.assertFalse((host / 'RimWorld.runtimeconfig.json').exists())
        self.assertEqual(sorted(os.listdir(host / 'Data')), ['Core'])
        self.assertEqual(sorted(os.listdir(host / 'Mods')), ['dep', 'target'])
        self.assertEqual(sorted(os.listdir(out / 'baseline' / 'host' / 'Mods')), ['dep'])
        deps = json.loads((host / f'{vh.WORKER_NAME}.deps.json').read_text(encoding='utf-8'))
        self.assertIn(f'{vh.WORKER_NAME}/{vh.TOOL_VERSION}', deps['libraries'])
        config = (out / 'target' / 'userdata' / 'Config' / 'ModsConfig.xml').read_text(encoding='utf-8')
        self.assertIn('<activeMods><li>ludeon.rimworld</li><li>test.dep</li><li>test.target</li></activeMods>', config)
        prefs = (out / 'target' / 'userdata' / 'Config' / 'Prefs.xml').read_text(encoding='utf-8')
        self.assertIn('<devMode>true</devMode><resetModsConfigOnCrash>false</resetModsConfigOnCrash>', prefs)
        self.assertEqual(json.loads((out / 'result.json').read_text(encoding='utf-8'))['status'], 'passed')

    def test_new_error_from_target_fails(self):
        self.fx.mod('bad')
        result, _ = self.fx.run(['*bad'])
        self.assertEqual(result['status'], 'failed')
        self.assertEqual([r['code'] for r in result['reasons']], ['newErrors'])
        self.assertIn('RWMT_Missing', result['diagnostics']['newInTarget'][0]['message'])

    def test_run_dirs_are_removed_unless_kept(self):
        self.fx.mod('target')
        _, out = self.fx.run(['*target'])
        self.assertFalse((out / 'target' / 'host').exists())
        self.assertTrue((out / 'target' / 'worker-result.json').is_file())

    def test_standard_runtime_is_experimental(self):
        self.fx.mod('target')
        result, out = self.fx.run(['*target'], runtime='standard', keep_run_dirs=True)
        self.assertEqual((result['status'], result['fidelity']), ('incomplete', 'experimental'))
        host = out / 'target' / 'host'
        self.assertFalse((host / 'System.Private.CoreLib.dll').exists())
        self.assertFalse((host / f'{vh.WORKER_NAME}.deps.json').exists())
        config = json.loads((host / f'{vh.WORKER_NAME}.runtimeconfig.json').read_text(encoding='utf-8'))
        self.assertNotIn('WaylithClr.LaxCallvirt', config['runtimeOptions']['configProperties'])

    def test_stale_result_and_mod_order_change_are_incomplete(self):
        for folder, code in [('stale', 'workerResultStale'), ('reorder', 'modOrderMismatch')]:
            with self.subTest(folder):
                self.fx.mod(folder)
                result, _ = self.fx.run([f'*{folder}'])
                self.assertEqual(result['status'], 'incomplete')
                self.assertIn(code, [r['code'] for r in result['reasons']])

    def test_missing_expected_patch_fails_and_missing_harmony_blocks(self):
        self.fx.mod('harmony', 'brrainz.harmony', harmony=True)
        self.fx.mod('nopatch')
        patch = {'owner': 'o', 'targetAssembly': 'a', 'targetType': 't', 'targetMethod': 'm', 'targetParameters': [],
                 'kind': 'postfix', 'patchType': 'p', 'patchMethod': 'q'}
        result, _ = self.fx.run(['harmony', '*nopatch'], levels=['A', 'B'], expectations={'harmonyPatches': [patch]})
        self.assertEqual(result['status'], 'failed')
        self.assertIn('harmonyPatchMissing', [r['code'] for r in result['reasons']])
        result, _ = self.fx.run(['*nopatch'], levels=['A', 'B'], expectations={'harmonyPatches': [patch]})
        self.assertEqual((result['status'], result['reasons'][0]['code']), ('blocked', 'harmonyMissing'))

    def test_timeout_kills_the_whole_process_group(self):
        self.fx.mod('hang')
        result, out = self.fx.run(['*hang'], limits={'timeoutSeconds': 10})
        self.assertEqual(result['status'], 'incomplete')
        process = result['process']['baseline']
        self.assertIsNone(process['killedFor'])
        self.assertEqual(result['process']['target']['killedFor'], 'timeout')
        self.assertIn('timeout', [r['code'] for r in result['reasons']])
        child = int((out / 'target' / 'child.pid').read_text(encoding='utf-8'))
        for _ in range(50):
            if not Path(f'/proc/{child}').exists() or 'Z' in Path(f'/proc/{child}/stat').read_text().split(')')[1][:3]:
                break
            time.sleep(0.1)
        else:
            self.fail('a descendant of the Worker survived the timeout kill')

    def test_log_limit_stops_the_worker(self):
        self.fx.mod('noisy')
        result, _ = self.fx.run(['*noisy'], limits={'logMiB': 1})
        self.assertEqual(result['process']['target']['killedFor'], 'logLimit')
        self.assertEqual(result['status'], 'incomplete')

    def test_memory_limit_stops_the_worker(self):
        self.fx.mod('memory')
        result, _ = self.fx.run(['*memory'], limits={'memoryMiB': 512})
        self.assertEqual(result['process']['target']['killedFor'], 'memoryLimit')
        self.assertFalse(result['process']['target']['enforcement']['memoryHard'])

    def test_baseline_cache_is_reused_only_for_identical_inputs(self):
        self.fx.mod('dep')
        self.fx.mod('target')
        cache = self.root / 'cache'
        first, _ = self.fx.run(['dep', '*target'], baseline_cache=cache)
        second, _ = self.fx.run(['dep', '*target'], baseline_cache=cache)
        self.assertFalse(first['diagnostics']['baselineCached'])
        self.assertTrue(second['diagnostics']['baselineCached'])
        (self.fx.mods / 'dep' / 'Defs' / 'a.xml').write_text('<Defs><!-- changed --></Defs>', encoding='utf-8')
        third, _ = self.fx.run(['dep', '*target'], baseline_cache=cache)
        self.assertFalse(third['diagnostics']['baselineCached'])

    def test_blocked_before_start(self):
        self.fx.mod('target')
        self.fx.mod('official', 'ludeon.rimworld.fake')
        cases = [
            ('platformUnsupported', ['*target'], {'platform': 'windows-x64'}),
            ('levelUnsupported', ['*target'], {'levels': ['A', 'B', 'C'], 'tests': ['t1']}),
            ('officialContentMissing', ['*target'], {'official': ['Core', 'Biotech']}),
            ('languageMissing', ['*target'], {'language': 'Klingon'}),
            ('modInvalid', ['*official'], {}),
            ('modMissing', ['*absent'], {}),
            ('invalidRequest', ['target'], {}),
        ]
        for code, mods, fields in cases:
            with self.subTest(code):
                result, _ = self.fx.run(mods, **fields)
                self.assertEqual((result['status'], result['executionStatus']), ('blocked', 'notStarted'))
                self.assertEqual(result['reasons'][0]['code'], code)
                self.assertEqual(vh.EXIT_CODES[result['status']], 2)

    def test_controller_error_is_reported_as_incomplete(self):
        self.fx.mod('target')
        (self.fx.worker / vh.WORKER_NAME).chmod(0o644)
        if os.geteuid() == 0 and os.access(self.fx.worker / vh.WORKER_NAME, os.X_OK):
            self.skipTest('cannot make the fake Worker unexecutable')
        result, out = self.fx.run(['*target'])
        self.assertEqual((result['status'], result['executionStatus']), ('incomplete', 'failed'))
        self.assertIn('controllerError', [r['code'] for r in result['reasons']])
        self.assertIn('PermissionError', result['process']['target']['controllerError'])
        self.assertTrue((out / 'result.json').is_file())

    def test_unknown_build_blocks_unless_allowed_as_experimental(self):
        self.fx.mod('target')
        self.fx.adapters = {}
        result, _ = self.fx.run(['*target'])
        self.assertEqual(result['reasons'][0]['code'], 'unknownBuild')
        result, _ = self.fx.run(['*target'], allow_unknown_build=True)
        self.assertEqual((result['status'], result['fidelity']), ('incomplete', 'experimental'))

    def test_missing_worker_and_nonempty_output_block(self):
        self.fx.mod('target')
        (self.fx.worker / f'{vh.WORKER_NAME}.dll').unlink()
        result, _ = self.fx.run(['*target'])
        self.assertEqual(result['reasons'][0]['code'], 'workerMissing')
        out = self.root / 'used'
        out.mkdir()
        (out / 'keep.txt').write_text('x', encoding='utf-8')
        result = vh.run_validation(self.fx.snapshot, self.fx.request(['*target']), out, self.fx.worker,
                                   adapters=self.fx.adapters, platform='linux-x64')
        self.assertEqual(result['reasons'][0]['code'], 'outputNotEmpty')
        self.assertEqual((out / 'keep.txt').read_text(encoding='utf-8'), 'x')


class ProductBoundaryTests(unittest.TestCase):
    def test_product_code_never_starts_the_official_game(self):
        root = Path(__file__).resolve().parents[1]
        for path in [root / 'tools' / 'validation_host.py', root / 'tools' / 'mod_preflight.py', root / 'tools' / 'preflight_gui.py',
                     *sorted((root / 'worker').rglob('*.cs'))]:
            text = path.read_text(encoding='utf-8')
            for forbidden in ('-QuitAfterBoot', "'-headless'", '-savedatafolder', 'official-comparison', 'compare_official'):
                self.assertNotIn(forbidden, text, f'{path} mentions {forbidden}')

    def test_worker_has_no_compile_time_game_reference(self):
        root = Path(__file__).resolve().parents[1]
        project = (root / 'worker' / 'RimWorldValidation.Worker' / 'RimWorldValidation.Worker.csproj').read_text(encoding='utf-8')
        self.assertNotIn('HintPath', project)
        self.assertNotIn('Assembly-CSharp', project)


if __name__ == '__main__':
    unittest.main()
