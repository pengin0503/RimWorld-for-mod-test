"""Following a game update in the Codex workflow: build version, upload provenance, qualification state.

Synthetic only: a fake game folder and fake R2 clients, never real R2 or game files.
"""
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from r2_fakes import GAME_VERSION, PROVENANCE_KEY, provenance_bytes, with_game_files
from test_codex_workflow import sample_index
from test_validation_host import TempCase
from tools import codex_workflow as cw
from tools import game_builds as gb

STALE = 'Game-Linux/Brutal.Glfw.dll'


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ProvenanceParsingTests(unittest.TestCase):
    def rows(self, **change):
        row = {'key': 'Game-Linux/Version.txt', 'size': 18, 'etag': '0' * 32, 'sha256': sha(b'v'),
               'byteVerified': True, 'hashMeaning': 'source-bytes', 'mode': '0755'}
        row.update(change)
        return gzip.compress(json.dumps([row]).encode())

    def test_owner_format_is_read(self):
        data = provenance_bytes({'Version.txt': (18, sha(b'v')), 'Data/Core/About/About.xml': (5, sha(b'a'))})
        self.assertEqual(cw.parse_provenance(data)['Data/Core/About/About.xml'], {'size': 5, 'sha256': sha(b'a')})

    def test_anything_unexpected_makes_it_unusable(self):
        for data in (b'not gzip', gzip.compress(b'{}'), gzip.compress(b'[]'), self.rows(hashMeaning='uploaded-bytes'),
                     self.rows(sha256='x'), self.rows(key='Workshop/1/About/About.xml'), self.rows(key='Game-Linux/../x'),
                     self.rows(size=-1),
                     provenance_bytes({'Assembly-CSharp.dll': (1, sha(b'x'))})):  # no Version.txt
            with self.subTest(data=data[:20]):
                self.assertIsNone(cw.parse_provenance(data))

    def test_symbolic_link_rows_have_no_hash(self):
        rows = [{'key': 'Game-Linux/Version.txt', 'size': 1, 'sha256': sha(b'v'), 'hashMeaning': 'source-bytes'},
                {'key': 'Game-Linux/libfoo.so', 'symlinkTarget': 'libfoo.so.1'}]
        parsed = cw.parse_provenance(gzip.compress(json.dumps(rows).encode()))
        self.assertEqual(parsed['libfoo.so'], {'size': None, 'sha256': None})

    def test_selection_leaves_out_stale_objects_and_checks_the_listing(self):
        provenance = {'Version.txt': {'size': 3, 'sha256': sha(b'v')}, 'A.dll': {'size': 4, 'sha256': sha(b'a')}}
        listed = [{'key': 'Game-Linux/Version.txt', 'size': 3}, {'key': 'Game-Linux/A.dll', 'size': 4},
                  {'key': STALE, 'size': 9}]
        self.assertEqual([i['key'] for i in cw.provenance_selection(listed, provenance)],
                         ['Game-Linux/Version.txt', 'Game-Linux/A.dll'])
        for broken in (listed[1:], [listed[0], {'key': 'Game-Linux/A.dll', 'size': 5}]):
            with self.subTest(broken=broken), self.assertRaises(cw.WorkflowError) as caught:
                cw.provenance_selection(broken, provenance)
            self.assertEqual(caught.exception.code, 'gameUploadInconsistent')


class PlannedVersionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    class NoR2:
        def get(self, *args, **kwargs):
            raise AssertionError('unexpected R2 GET')

        def list_prefix(self, prefix):
            raise AssertionError('unexpected R2 listing')

    def test_prepared_snapshot_decides_without_r2(self):
        (self.root / 'game-snapshot').mkdir()
        (self.root / 'game-snapshot' / 'snapshot.json').write_text(json.dumps({'version': '1.7.4985 rev1269'}))
        self.assertEqual(cw.planned_game_version(self.root, self.NoR2()), '1.7.4985 rev1269')

    def test_otherwise_game_version_txt_is_read_from_r2(self):
        client = with_game_files(self.NoR2)()
        self.assertEqual(cw.planned_game_version(self.root, client), '1.7.5014 rev1195')
        self.assertEqual(client.exact_requests, ['Game-Linux/Version.txt'])

    def test_other_major_minor_or_garbage_stops(self):
        for version, code in ((b'1.8.1 rev1\n', 'unsupportedGameVersion'), (b'', 'invalidGameVersion'),
                              (b'\xff\xfe', 'invalidGameVersion'), (b'hello', 'unsupportedGameVersion')):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(cw.WorkflowError) as caught:
                    cw.planned_game_version(Path(tmp), with_game_files(self.NoR2, version=version)())
                self.assertEqual(caught.exception.code, code)

    def test_fetch_mods_plans_for_that_build(self):
        """A MOD that supports only 1.6 gets its v1.6 dependencies on 1.7.5014 (the new fallback)."""
        sample_index(self.root / 'index.zip')
        about = (b'<ModMetaData><packageId>author.example</packageId><supportedVersions><li>1.6</li></supportedVersions>'
                 b'<modDependenciesByVersion><v1.6><li><packageId>brrainz.harmony</packageId></li></v1.6>'
                 b'</modDependenciesByVersion></ModMetaData>')
        harmony = b'<ModMetaData><packageId>brrainz.harmony</packageId></ModMetaData>'
        contents = {'1234567890': about, '2009463077': harmony}

        class FakeR2:
            def list_prefix(self, prefix):
                return [{'key': prefix + 'About/About.xml', 'size': len(contents[prefix.split('/')[1]])}]

            def get(self, key, dest, size, *, refresh=False):
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(contents[key.split('/')[1]])
                return 'downloaded'

        def fetch(version, private):
            args = SimpleNamespace(private_root=self.root / private, index_zip=str(self.root / 'index.zip'), aws='aws',
                                   dependency=[], target='Example', language='English', scope='validation', refresh=False)
            with patch.object(cw, 'r2_client', return_value=with_game_files(FakeR2, version=version)()):
                return cw.fetch_mods(args)

        result = fetch(GAME_VERSION, 'p5014')
        self.assertEqual(result['gameVersion'], '1.7.5014 rev1195')
        self.assertEqual([m['packageId'] for m in json.loads(Path(result['request']).read_text())['mods']],
                         ['brrainz.harmony', 'author.example'])
        result = fetch(b'1.7.4985 rev1269\r\n', 'p4985')
        self.assertEqual([m['packageId'] for m in json.loads(Path(result['request']).read_text())['mods']],
                         ['author.example'])


class PrepareWithProvenanceTests(TempCase):
    """prepare() on a fake game-source that is already complete (every GET is a cache hit)."""

    def setUp(self):
        super().setUp()
        (self.fx.game / 'Version.txt').write_bytes(GAME_VERSION)
        self.files = {p.relative_to(self.fx.game).as_posix(): p for p in sorted(self.fx.game.rglob('*')) if p.is_file()}

    def provenance(self, **override):
        rows = {rel: (path.stat().st_size, sha(path.read_bytes())) for rel, path in self.files.items()}
        rows.update(override)
        return provenance_bytes(rows)

    def client(self, provenance, extra_listing=(), sizes=None):
        files, gets = self.files, []

        class FakeR2:
            def list_prefix(self, prefix):
                if prefix != 'Game-Linux/':
                    raise AssertionError('unexpected prefix')
                rows = [{'key': 'Game-Linux/' + rel, 'size': (sizes or {}).get(rel, path.stat().st_size)}
                        for rel, path in files.items()]
                return rows + [{'key': key, 'size': 9} for key in extra_listing]

            def get(self, key, dest, size, *, refresh=False):
                gets.append(key)
                if key == STALE:
                    raise AssertionError('an object of the previous build was downloaded')
                return 'cached'

        client = with_game_files(FakeR2, provenance=provenance)()
        client.gets = gets
        return client

    def prepare(self, client):
        with patch.object(cw, 'r2_client', return_value=client):
            return cw.prepare(SimpleNamespace(private_root=self.root, aws='aws', refresh=False))

    def test_stale_objects_are_left_out_and_hashes_verified(self):
        client = self.client(self.provenance(), extra_listing=[STALE])
        result = self.prepare(client)
        self.assertEqual(result['status'], 'prepared')
        self.assertEqual(result['gameSource'], {'provenance': 'used', 'sha256Verified': True,
                                                'notInProvenanceSkipped': [STALE]})
        self.assertNotIn(STALE, client.gets)
        self.assertEqual(result['version'], '1.7.5014 rev1195')
        self.assertEqual(result['qualification']['state'], 'notQualified')

    def test_provenance_of_another_build_stops(self):
        client = self.client(self.provenance(**{'Version.txt': (len(GAME_VERSION), sha(b'1.7.4985 rev1269\r\n'))}))
        with self.assertRaises(cw.WorkflowError) as caught:
            self.prepare(client)
        self.assertEqual(caught.exception.code, 'gameUploadInconsistent')
        self.assertFalse((self.root / 'game-snapshot').exists())

    def test_changed_file_stops(self):
        size = self.files['RimWorld.dll'].stat().st_size
        client = self.client(self.provenance(**{'RimWorld.dll': (size, sha(b'other bytes'))}))
        with self.assertRaises(cw.WorkflowError) as caught:
            self.prepare(client)
        self.assertEqual(caught.exception.code, 'gameUploadInconsistent')
        self.assertIn('RimWorld.dll', str(caught.exception))

    def test_upload_in_progress_stops_before_any_download(self):
        client = self.client(self.provenance(), sizes={'RimWorld.dll': 1})
        with self.assertRaises(cw.WorkflowError) as caught:
            self.prepare(client)
        self.assertEqual(caught.exception.code, 'gameUploadInconsistent')
        self.assertEqual(client.gets, [])  # no game file was requested (the provenance GET is the helper's)

    def test_leftover_file_of_an_earlier_fetch_stops(self):
        provenance = self.provenance()
        (self.fx.game / 'Leftover.dll').write_bytes(b'old build')
        with self.assertRaises(cw.WorkflowError) as caught:
            self.prepare(self.client(provenance))
        self.assertEqual(caught.exception.code, 'gameSourceStale')

    def test_without_provenance_the_listing_is_used_as_before(self):
        result = self.prepare(self.client(None, extra_listing=[]))
        self.assertEqual(result['gameSource'], {'provenance': 'absent'})

    def test_unreadable_provenance_is_reported_and_not_used(self):
        result = self.prepare(self.client(b'not gzip'))
        self.assertEqual(result['gameSource'], {'provenance': 'unreadable'})


class QualificationStateTests(TempCase):
    def prepared(self, version):
        (self.fx.game / 'Version.txt').write_text(version, encoding='utf-8')
        return self.fx.prepare()

    def test_states(self):
        info = self.prepared('1.7.6000 rev3\n')
        with patch.dict(os.environ, {gb.STORE_ENV: ''}):
            self.assertEqual(cw.qualification_state(info)['state'], 'notQualified')
        store = self.root / 'store'
        store.mkdir()
        files = info['files']
        body = {'recordType': gb.RECORD_TYPE, 'schemaVersion': 1, 'gameVersion': '1.7.6000 rev3',
                'buildId': '1.7.6000-rev3', 'method': 'automatic',
                'identitySha256': {n: files[n]['sha256'] for n in gb.IDENTITY_FILES}, 'qualified': []}
        (store / 'r.json').write_text(json.dumps(body), encoding='utf-8')
        with patch.dict(os.environ, {gb.STORE_ENV: str(store)}):
            self.assertEqual(cw.qualification_state(info)['state'], 'privateRecord')
        adapters = {'rimworld-1.7.6000-rev3': gb.adapter_from_record(gb.validate_record(body), source='committed')}
        with patch.object(cw.validation_host, 'ADAPTERS', adapters):
            self.assertEqual(cw.qualification_state(info), {'state': 'reviewedRecord', 'adapter': 'rimworld-1.7.6000-rev3'})

    def test_unsupported_family(self):
        info = self.prepared('1.8.1 rev1\n')
        self.assertEqual(cw.qualification_state(info)['state'], 'unsupportedVersion')


if __name__ == '__main__':
    unittest.main()
