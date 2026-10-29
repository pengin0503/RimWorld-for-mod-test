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
            (root / 'static-audit' / 'input').symlink_to(target, target_is_directory=True)
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

    def test_wrong_ref_does_not_contact_r2(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{**ENV,'GITHUB_REF':'refs/heads/other'},clear=True), patch.object(a.cw,'r2_session',side_effect=AssertionError('R2 contacted')):
            with self.assertRaises(ValueError): a.prepare(Path(d))

    def test_publication_rejects_stale_or_hostile_metadata(self):
        raw={**a.pv.current_identity(ENV),'verified':True,'metadata':{'types':[{'type':'Verse.Game','methods':[{'name':'InitNewGame','signature':'System.Void ()','calls':['PRIVATE']}]}]},'exception':'PRIVATE'}
        safe=a.public_summary(raw,a.pv.current_identity(ENV))
        self.assertNotIn('PRIVATE',json.dumps(safe)); self.assertFalse(safe['c0Passed'])
        raw['commit']='b'*40
        self.assertFalse(a.public_summary(raw,a.pv.current_identity(ENV))['verified'])
