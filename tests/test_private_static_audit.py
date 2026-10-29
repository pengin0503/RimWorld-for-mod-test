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
            def get(self,key,dest,size,refresh=False): dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(data[ke…3401 tokens truncated…n            result = a.publish(root)
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

    def test_wrong_ref_does_not_contact_r2(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{**ENV,'GITHUB_REF':'refs/heads/other'},clear=True), patch.object(a.cw,'r2_session',side_effect=AssertionError('R2 contacted')):
            with self.assertRaises(ValueError): a.prepare(Path(d))

    def test_publication_rejects_stale_or_hostile_metadata(self):
        raw={**a.pv.current_identity(ENV),'verified':True,'metadata':{'types':[{'type':'Verse.Game','methods':[{'name':'InitNewGame','signature':'System.Void ()','calls':['PRIVATE']}]}]},'exception':'PRIVATE'}
        safe=a.public_summary(raw,a.pv.current_identity(ENV))
        self.assertNotIn('PRIVATE',json.dumps(safe)); self.assertFalse(safe['c0Passed'])
        raw['commit']='b'*40
        self.assertFalse(a.public_summary(raw,a.pv.current_identity(ENV))['verified'])
