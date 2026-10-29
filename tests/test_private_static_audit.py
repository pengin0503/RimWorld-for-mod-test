import contextlib
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import private_static_audit as a
from tests.test_private_validation import ENV

class AuditTests(unittest.TestCase):
    def test_download_only_fixed_files_and_verify_hashes_before_readiness(self):
        data={'Version.txt':b'1.7.4985 rev1269\n','Assembly-CSharp.dll':b'own synthetic PE','libcoreclr.so':b'own synthetic CLR'}
        expected={n:hashlib.sha256(v).hexdigest() for n,v in data.items() if n!='Version.txt'}
        class R2:
            def list_prefix(self,prefix): return [{'key':'Game-Linux/'+n,'size':len(v)} for n,v in data.items() if ('Game-Linux/'+n).startswith(prefix)]
            def get(self,key,dest,size,refresh=False): dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(data[key.removeprefix('Game-Linux/')]); return 'downloaded'
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,ENV,clear=True), patch.object(a,'EXPECTED',expected), patch.object(a.cw,'r2_session',return_value=contextlib.nullcontext(R2())):
            root=Path(d); a.prepare(root)
            record=json.loads((a.session_path(root)/'manifest.json').read_text())
            self.assertTrue(record['verified']); self.assertEqual(record['files'],3)
            self.assertEqual(sorted(p.name for p in (a.session_path(root)/'input').iterdir()),['Assembly-CSharp.dll','Version.txt','libcoreclr.so'])
            (a.session_path(root)/'input/Assembly-CSharp.dll').write_bytes(b'corrupt')
            self.assertFalse(a.verify(root))

    def test_metadata_budget_rejects_before_any_download(self):
        class R2:
            def __init__(self): self.downloads = []
            def list_prefix(self, prefix):
                return [{'key': prefix, 'size': 64 * 1024 * 1024 + 1}]
            def get(self, key, dest, size, refresh=False): self.downloads.append(key)
        client = R2()
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, ENV, clear=True), patch.object(a.cw, 'r2_session', return_value=contextlib.nullcontext(client)):
            with self.assertRaises(ValueError): a.prepare(Path(d))
            self.assertEqual(client.downloads, [])

    def test_version_rejects_leading_or_trailing_spaces(self):
        with tempfile.TemporaryDirectory() as d, patch.object(a, 'EXPECTED', {}):
            directory = Path(d) / 'static-audit' / 'input'
            directory.mkdir(parents=True)
            (directory / 'Version.txt').write_text(' 1.7.4985 rev1269 \n')
            self.assertFalse(a.verify_directory(directory))

    def test_rejects_nested_symlink_for_snapshot_inputs(self):
        with tempfile.TemporaryDirectory() as d, patch.object(a, 'EXPECTED', {}):
            root = Path(d)
            target = root / 'elsewhere'
            target.mkdir()
            (target / 'Version.txt').write_text('1.7.4985 rev1269\n')
            (root / 'static-audit').mkdir()
            try: (root / 'static-audit' / 'input').symlink_to(target, target_is_directory=True)
            except OSError as exc: self.skipTest('symlink unavailable: ' + str(exc))
            self.assertFalse(a.verify_directory(root / 'static-audit/input'))

    def test_download_with_size_different_from_metadata_is_rejected(self):
        data = {'Version.txt': b'1.7.4985 rev1269\n', 'sample.dll': b'synthetic'}
        expected = {'sample.dll': hashlib.sha256(data['sample.dll']).hexdigest()}
        class R2:
            def list_prefix(self, prefix):
                name = prefix.removeprefix('Game-Linux/')
                return [{'key': prefix, 'size': len(data[name]) + 1}]
            def get(self, key, dest, size, refresh=False):
                dest.write_bytes(data[key.removeprefix('Game-Linux/')])
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, ENV, clear=True), patch.object(a, 'EXPECTED', expected), patch.object(a.cw, 'r2_session', return_value=contextlib.nullcontext(R2())):
            with self.assertRaises(ValueError): a.prepare(Path(d))
            record = json.loads((a.session_path(Path(d)) / 'manifest.json').read_text())
            self.assertFalse(record['verified'])

    def test_valid_snapshot_is_reused_without_r2(self):
        data = {'Version.txt': b'1.7.4985 rev1269\n', 'sample.dll': b'synthetic'}
        expected = {'sample.dll': hashlib.sha256(data['sample.dll']).hexdigest()}
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, ENV, clear=True), patch.object(a, 'EXPECTED', expected), patch.object(a.cw, 'r2_session', side_effect=AssertionError('R2 contacted')):
            root = Path(d)
            snapshot = root / 'game-snapshot/game'
            snapshot.mkdir(parents=True)
            for name, contents in data.items(): (snapshot / name).write_bytes(contents)
            record = a.prepare(root)
            self.assertTrue(record['verified'])
            self.assertEqual((a.session_path(root) / 'input/sample.dll').read_bytes(), data['sample.dll'])

    def test_oversized_snapshot_file_is_not_read(self):
        with tempfile.TemporaryDirectory() as d, patch.object(a, 'EXPECTED', {'sample.dll': '0' * 64}):
            directory = Path(d) / 'static-audit/input'
            directory.mkdir(parents=True)
            (directory / 'Version.txt').write_text('1.7.4985 rev1269\n')
            with (directory / 'sample.dll').open('wb') as f: f.truncate(64 * 1024 * 1024 + 1)
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('unbounded read')):
                self.assertFalse(a.verify_directory(directory))

    def test_duplicate_prepare_invalidates_previous_success(self):
        data = {'Version.txt': b'1.7.4985 rev1269\n', 'sample.dll': b'synthetic'}
        expected = {'sample.dll': hashlib.sha256(data['sample.dll']).hexdigest()}
        class R2:
            def list_prefix(self, prefix):
                name = prefix.removeprefix('Game-Linux/')
                return [{'key': prefix, 'size': len(data[name])}]
            def get(self, key, dest, size, refresh=False):
                dest.write_bytes(data[key.removeprefix('Game-Linux/')])
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, ENV, clear=True), patch.object(a, 'EXPECTED', expected), patch.object(a.cw, 'r2_session', return_value=contextlib.nullcontext(R2())):
            root = Path(d)
            self.assertTrue(a.prepare(root)['verified'])
            with self.assertRaises(ValueError): a.prepare(root)
            self.assertFalse(json.loads((a.session_path(root) / 'manifest.json').read_text())['verified'])

    def test_distinct_run_ids_have_independent_sessions(self):
        data = {'Version.txt': b'1.7.4985 rev1269\n', 'sample.dll': b'synthetic'}
        expected = {'sample.dll': hashlib.sha256(data['sample.dll']).hexdigest()}
        class R2:
            def list_prefix(self, prefix):
                name = prefix.removeprefix('Game-Linux/')
                return [{'key': prefix, 'size': len(data[name])}]
            def get(self, key, dest, size, refresh=False):
                dest.write_bytes(data[key.removeprefix('Game-Linux/')])
        with tempfile.TemporaryDirectory() as d, patch.object(a, 'EXPECTED', expected), patch.object(a.cw, 'r2_session', return_value=contextlib.nullcontext(R2())):
            with patch.dict(os.environ, ENV, clear=True): self.assertTrue(a.prepare(Path(d))['verified'])
            with patch.dict(os.environ, {**ENV, 'GITHUB_RUN_ID': '900'}, clear=True): self.assertTrue(a.prepare(Path(d))['verified'])

    def test_partial_snapshot_reuses_verified_files(self):
        data = {'Version.txt': b'1.7.4985 rev1269\n', 'sample.dll': b'synthetic', 'other.dll': b'other'}
        expected = {name: hashlib.sha256(data[name]).hexdigest() for name in ('sample.dll', 'other.dll')}
        class R2:
            def __init__(self): self.downloads = []
            def list_prefix(self, prefix):
                name = prefix.removeprefix('Game-Linux/')
                return [{'key': prefix, 'size': len(data[name])}]
            def get(self, key, dest, size, refresh=False):
                self.downloads.append(key)
                dest.write_bytes(data[key.removeprefix('Game-Linux/')])
        client = R2()
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, ENV, clear=True), patch.object(a, 'EXPECTED', expected), patch.object(a.cw, 'r2_session', return_value=contextlib.nullcontext(client)):
            root = Path(d); snapshot = root / 'game-snapshot/game'; snapshot.mkdir(parents=True)
            (snapshot / 'sample.dll').write_bytes(data['sample.dll'])
            self.assertTrue(a.prepare(root)['verified'])
            self.assertNotIn('Game-Linux/sample.dll', client.downloads)

    def test_prepared_manifest_records_sources_and_hashes(self):
        data = {'Version.txt': b'1.7.4985 rev1269\n', 'sample.dll': b'synthetic'}
        expected = {'sample.dll': hashlib.sha256(data['sample.dll']).hexdigest()}
        class R2:
            def list_prefix(self, prefix):
                name = prefix.removeprefix('Game-Linux/')
                return [{'key': prefix, 'size': len(data[name])}]
            def get(self, key, dest, size, refresh=False): dest.write_bytes(data[key.removeprefix('Game-Linux/')])
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, ENV, clear=True), patch.object(a, 'EXPECTED', expected), patch.object(a.cw, 'r2_session', return_value=contextlib.nullcontext(R2())):
            root = Path(d); snapshot = root / 'game-snapshot/game'; snapshot.mkdir(parents=True)
            (snapshot / 'sample.dll').write_bytes(data['sample.dll'])
            result = a.prepare(root)
            self.assertEqual(result['inputs']['sample.dll']['source'], 'snapshot')
            self.assertEqual(result['inputs']['sample.dll']['sha256'], expected['sample.dll'])
            self.assertEqual(result['inputs']['Version.txt']['source'], 'r2')
            self.assertEqual(result['inputs']['Version.txt']['size'], len(data['Version.txt']))

    def test_load_session_rechecks_identity_manifest_and_bytes(self):
        data = {'Version.txt': b'1.7.4985 rev1269\n', 'sample.dll': b'synthetic'}
        expected = {'sample.dll': hashlib.sha256(data['sample.dll']).hexdigest()}
        class R2:
            def list_prefix(self, prefix):
                name = prefix.removeprefix('Game-Linux/')
                return [{'key': prefix, 'size': len(data[name])}]
            def get(self, key, dest, size, refresh=False): dest.write_bytes(data[key.removeprefix('Game-Linux/')])
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, ENV, clear=True), patch.object(a, 'EXPECTED', expected), patch.object(a.cw, 'r2_session', return_value=contextlib.nullcontext(R2())):
            root = Path(d); a.prepare(root)
            self.assertTrue(a.load_session(root)['verified'])
            (a.session_path(root) / 'input/sample.dll').write_bytes(b'changed')
            with self.assertRaises(ValueError): a.load_session(root)

    def test_unrecognized_type_atoms_are_never_published(self):
        identity = a.pv.current_identity(ENV)
        overload = {'token': 100663297, 'return': {'kind': 'named', 'name': 'PRIVATE.Secret'},
                    'parameters': [], 'genericCount': 0, 'static': False, 'visibility': 'Public', 'calls': []}
        raw = {**identity, 'verified': True, 'types': [{'id': 'game', 'found': True,
              'methods': [{'name': 'InitNewGame', 'overloads': [overload]}]}]}
        result = a.public_summary(raw, identity)
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertEqual(result['staticAuditStatus'], 'incomplete')
        self.assertFalse(result['c0Passed'])
        self.assertEqual(result['types'][0]['methods'][0]['unreadableTokens'], [100663297])

    def test_known_signature_is_rebuilt_from_fixed_atoms(self):
        signature = {'kind': 'byref', 'element': {'kind': 'array', 'rank': 1,
                    'element': {'kind': 'primitive', 'name': 'Int32'}}}
        self.assertEqual(a.normalized_type(signature), 'System.Int32[]&')
        with self.assertRaises(ValueError): a.normalized_type({'kind': 'named', 'name': 'System.PRIVATE'})

    def test_public_summary_rebuilds_known_signature_without_unknown_fields(self):
        identity = a.pv.current_identity(ENV)
        methods = [{'name': name, 'overloads': []} for name in a.TARGETS['game']]
        methods[0]['overloads'] = [{'token': 100663297, 'return': {'kind': 'primitive', 'name': 'Void'},
            'parameters': [{'kind': 'primitive', 'name': 'Int32'}], 'genericCount': 0, 'static': False,
            'visibility': 'Public', 'calls': [], 'private': 'PRIVATE'}]
        raw = {**identity, 'verified': True, 'types': [{'id': 'game', 'found': True, 'methods': methods}]}
        result = a.public_summary(raw, identity)
        self.assertEqual(result['types'][0]['methods'][0]['signatures'][0], 'instance public System.Void (System.Int32)')
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertEqual(result['staticAuditStatus'], 'incomplete')

    def test_scanner_supervisor_receives_finite_timeout_and_memory_limit(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, ENV, clear=True):
            root = Path(d); session = a.session_path(root); (session / 'input').mkdir(parents=True)
            with patch.object(a, 'load_session', return_value={'verified': True}), patch.object(a.pv, 'run_command', return_value={'exitCode': 1, 'interrupted': False, 'seconds': 0}) as run:
                with self.assertRaises(ValueError): a.scan(root, Path('/synthetic/scanner.dll'))
                self.assertLessEqual(run.call_args.kwargs['timeout'], 120)
                self.assertEqual(run.call_args.kwargs['memory_limit'], 2 * 1024**3)

    def test_publish_revalidates_inputs_before_trusting_scanner_result(self):
        identity = a.pv.current_identity(ENV)
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, ENV, clear=True), patch.object(a, 'load_session', side_effect=ValueError('changed')):
            root = Path(d); session = a.session_path(root); session.mkdir(parents=True)
            (session / 'scan.json').write_text(json.dumps({**identity, 'verified': True, 'types': []}))
            result = a.publish(root)
            self.assertFalse(result['binaryVerified'])
            self.assertEqual(result['staticAuditStatus'], 'incomplete')

    def test_workflow_keeps_credentials_in_preparation_step(self):
        text = (Path(__file__).resolve().parents[1] / '.github/workflows/linux-private-c-audit.yml').read_text()
        self.assertIn("github.ref == 'refs/heads/main'", text)
        self.assertIn('test "$(git rev-parse HEAD)" = "$GITHUB_SHA"', text)
        prepare = text.split('      - name: Prepare fixed private inputs', 1)[1].split('      - name:', 1)[0]
        self.assertIn('R2_ACCESS_KEY_ID', prepare)
        self.assertNotIn('secrets.', text.replace(prepare, ''))
        self.assertNotIn('upload-artifact', text)

    def test_absent_type_cannot_claim_found_methods(self):
        identity = a.pv.current_identity(ENV)
        types = [{'id': target, 'found': False, 'methods': [{'name': name, 'overloads': []} for name in names]} for target, names in a.TARGETS.items()]
        types[0]['methods'][0]['overloads'] = [{'return': {'kind': 'primitive', 'name': 'Void'}, 'parameters': [], 'genericCount': 0, 'static': False, 'visibility': 'Public', 'calls': []}]
        result = a.public_summary({**identity, 'verified': True, 'types': types}, identity)
        self.assertEqual(result['staticAuditStatus'], 'incomplete')

    def test_revalidation_rejects_symlinked_audit_parent(self):
        data = {'Version.txt': b'1.7.4985 rev1269\n', 'sample.dll': b'synthetic'}
        expected = {'sample.dll': hashlib.sha256(data['sample.dll']).hexdigest()}
        class R2:
            def list_prefix(self, prefix):
                name = prefix.removeprefix('Game-Linux/')
                return [{'key': prefix, 'size': len(data[name])}]
            def get(self, key, dest, size, refresh=False): dest.write_bytes(data[key.removeprefix('Game-Linux/')])
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, ENV, clear=True), patch.object(a, 'EXPECTED', expected), patch.object(a.cw, 'r2_session', return_value=contextlib.nullcontext(R2())):
            root = Path(d); a.prepare(root)
            (root / 'static-audit').rename(root / 'moved')
            try: (root / 'static-audit').symlink_to(root / 'moved', target_is_directory=True)
            except OSError as exc: self.skipTest('symlink unavailable: ' + str(exc))
            with self.assertRaises(ValueError): a.load_session(root)

    def test_version_rejects_carriage_return_without_newline(self):
        with tempfile.TemporaryDirectory() as d, patch.object(a, 'EXPECTED', {}):
            directory = Path(d); (directory / 'Version.txt').write_bytes(b'1.7.4985 rev1269\r')
            self.assertFalse(a.verify_directory(directory))

    def test_duplicate_r2_metadata_stops_before_download(self):
        class R2:
            def __init__(self): self.downloads = []
            def list_prefix(self, key): return [{'key': key, 'size': 1}, {'key': key, 'size': 1}]
            def get(self, key, dest, size, refresh=False): self.downloads.append(key)
        client = R2()
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, ENV, clear=True), patch.object(a.cw, 'r2_session', return_value=contextlib.nullcontext(client)):
            with self.assertRaises(ValueError): a.prepare(Path(d))
            self.assertEqual(client.downloads, [])

    def test_total_budget_rejects_before_download(self):
        class R2:
            def __init__(self): self.downloads = []
            def list_prefix(self, key): return [{'key': key, 'size': 40 * 1024 * 1024}]
            def get(self, key, dest, size, refresh=False): self.downloads.append(key)
        client = R2()
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, ENV, clear=True), patch.object(a.cw, 'r2_session', return_value=contextlib.nullcontext(client)):
            with self.assertRaises(ValueError): a.prepare(Path(d))
            self.assertEqual(client.downloads, [])

    def test_supervisor_rejects_log_overflow_after_fast_exit(self):
        class Child:
            returncode = 0
            def __init__(self, command, stdout, **kwargs):
                stdout.write(b'x' * (8 * 1024 * 1024 + 1)); stdout.flush()
                Path(command[2]).write_text(json.dumps({'exitCode': 0, 'strayProcessesKilled': False}))
            def poll(self): return 0
            def wait(self): return 0
        with tempfile.TemporaryDirectory() as d, patch.object(a.pv, 'native_process_available', return_value=True), patch.object(a.pv.subprocess, 'Popen', Child):
            outcome = a.pv.run_command(['synthetic'], Path(d) / 'private.log', timeout=120, memory_limit=2*1024**3)
            self.assertTrue(outcome['interrupted'])

    def test_adapter_file_set_change_is_rejected_before_r2(self):
        modified = dict(a.ADAPTER)
        modified['sha256'] = {**modified['sha256'], 'unexpected.dll': '0' * 64}
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, ENV, clear=True), patch.object(a, 'ADAPTER', modified), patch.object(a.cw, 'r2_session', side_effect=AssertionError('R2 contacted')):
            with self.assertRaises(ValueError): a.prepare(Path(d))

    def test_nonfinite_unknown_value_prevents_completed_status(self):
        identity = a.pv.current_identity(ENV)
        types = [{'id': target, 'found': False, 'methods': [{'name': name, 'overloads': []} for name in names]} for target, names in a.TARGETS.items()]
        types[0]['private'] = float('nan')
        result = a.public_summary({**identity, 'verified': True, 'types': types}, identity)
        self.assertEqual(result['staticAuditStatus'], 'incomplete')
        self.assertNotIn('NaN', json.dumps(result))

    def test_scanner_child_environment_does_not_inherit_secrets(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'PATH': '/usr/bin', 'AWS_SECRET_ACCESS_KEY': 'PRIVATE', 'GITHUB_TOKEN': 'PRIVATE', 'R2_ENDPOINT': 'PRIVATE'}, clear=True):
            child = a.pv.child_environment(Path(d))
            self.assertEqual(child['PATH'], '/usr/bin')
            self.assertNotIn('AWS_SECRET_ACCESS_KEY', child)
            self.assertNotIn('GITHUB_TOKEN', child)
            self.assertNotIn('R2_ENDPOINT', child)

    def test_scan_aggregates_fixed_images_and_cannot_run_twice(self):
        def run(command, log, **kwargs):
            types = [{'id': target, 'found': False, 'methods': [{'name': name, 'overloads': []} for name in names]} for target, names in a.TARGETS.items()]
            Path(command[-1]).write_text(json.dumps({'sha256': command[-2], 'types': types}))
            return {'exitCode': 0, 'interrupted': False, 'seconds': 0}
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, ENV, clear=True), patch.object(a, 'load_session', return_value={'verified': True}), patch.object(a.pv, 'run_command', side_effect=run) as runner:
            root = Path(d); (a.session_path(root) / 'input').mkdir(parents=True)
            output = a.scan(root, Path('/synthetic/scanner.dll'))
            self.assertEqual(runner.call_count, 5)
            self.assertEqual(a.public_summary(output, a.pv.current_identity())['staticAuditStatus'], 'completed')
            with self.assertRaises(ValueError): a.scan(root, Path('/synthetic/scanner.dll'))
            self.assertFalse(json.loads((a.session_path(root) / 'scan.json').read_text())['verified'])

    def test_wrong_ref_does_not_contact_r2(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{**ENV,'GITHUB_REF':'refs/heads/other'},clear=True), patch.object(a.cw,'r2_session',side_effect=AssertionError('R2 contacted')):
            with self.assertRaises(ValueError): a.prepare(Path(d))

    def test_publication_rejects_stale_or_hostile_metadata(self):
        raw={**a.pv.current_identity(ENV),'verified':True,'metadata':{'types':[{'type':'Verse.Game','methods':[{'name':'InitNewGame','signature':'System.Void ()','calls':['PRIVATE']}]}]},'exception':'PRIVATE'}
        safe=a.public_summary(raw,a.pv.current_identity(ENV))
        self.assertNotIn('PRIVATE',json.dumps(safe)); self.assertFalse(safe['c0Passed'])
        raw['commit']='b'*40
        self.assertFalse(a.public_summary(raw,a.pv.current_identity(ENV))['verified'])
