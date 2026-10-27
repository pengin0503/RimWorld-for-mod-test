"""Synthetic dependency graphs: no index or game assets leave private storage."""
import unittest
import xml.etree.ElementTree as ET
from tools import codex_workflow as cw


def metadata(package, children=''):
    return ET.fromstring(f'<ModMetaData><packageId>{package}</packageId>{children}</ModMetaData>')


class DependencyResolutionTests(unittest.TestCase):
    def test_required_dependency_precedes_target(self):
        index = {'mods': [{'workshop_id': '1', 'package_id': 'author.target', 'name': 'Target'},
                          {'workshop_id': '2', 'package_id': 'author.dep', 'name': 'Dependency'}]}
        data = {'author.target': metadata('author.target', '<modDependencies><li><packageId>author.dep</packageId></li></modDependencies>'),
                'author.dep': metadata('author.dep')}
        order = cw.resolve_mod_graph(index, ['author.target'], lambda mod: data[mod['packageId']])
        self.assertEqual([mod['packageId'] for mod in order], ['author.dep', 'author.target'])

    def test_cycle_is_blocked(self):
        index = {'mods': [{'workshop_id': '1', 'package_id': 'a', 'name': 'A'},
                          {'workshop_id': '2', 'package_id': 'b', 'name': 'B'}]}
        data = {'a': metadata('a', '<loadAfter><li>b</li></loadAfter>'),
                'b': metadata('b', '<loadAfter><li>a</li></loadAfter>')}
        with self.assertRaises(cw.WorkflowError) as caught:
            cw.resolve_mod_graph(index, ['a'], lambda mod: data[mod['packageId']])
        self.assertEqual(caught.exception.code, 'dependencyCycle')

    def test_fetch_mods_follows_metadata_before_payload(self):
        import json, tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        from tests.test_codex_workflow import sample_index
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / 'index.zip'
            sample_index(archive)
            contents = {
                '1234567890': b'<ModMetaData><packageId>author.example</packageId><modDependencies><li><packageId>brrainz.harmony</packageId></li></modDependencies></ModMetaData>',
                '2009463077': b'<ModMetaData><packageId>brrainz.harmony</packageId></ModMetaData>',
            }
            class FakeR2:
                def list_prefix(self, prefix):
                    return [{'key': prefix + 'About/About.xml', 'size': len(contents[prefix.split('/')[1]])}]
                def get(self, key, dest, size, *, refresh=False):
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(contents[key.split('/')[1]])
                    return 'downloaded'
            args = SimpleNamespace(private_root=root / 'private', index_zip=str(archive), aws='aws',
                                   dependency=[], target='Example', language='English', scope='validation', refresh=False)
            with patch.object(cw, 'r2_client', return_value=FakeR2()):
                result = cw.fetch_mods(args)
            request = json.loads(Path(result['request']).read_text())
            self.assertEqual([m['packageId'] for m in request['mods']], ['brrainz.harmony', 'author.example'])
            self.assertTrue(request['mods'][-1]['target'])

    def test_official_dlc_is_reported(self):
        index = {'mods': [{'workshop_id': '1', 'package_id': 'a', 'name': 'A'}]}
        meta = metadata('a', '<modDependencies><li><packageId>Ludeon.RimWorld.Biotech</packageId></li></modDependencies>')
        with self.assertRaises(cw.WorkflowError) as caught:
            cw.resolve_mod_graph(index, ['a'], lambda _: meta)
        self.assertEqual(caught.exception.code, 'officialContentMissing')
        self.assertIn('Biotech', str(caught.exception))

    def test_missing_index_dependency_blocks(self):
        index = {'mods': [{'workshop_id': '1', 'package_id': 'a', 'name': 'A'}]}
        meta = metadata('a', '<loadAfter><li>unknown.mod</li></loadAfter>')
        with self.assertRaises(cw.WorkflowError) as caught:
            cw.resolve_mod_graph(index, ['a'], lambda _: meta)
        self.assertEqual(caught.exception.code, 'missingDependencies')

    def test_local_target_order_constraints_are_included(self):
        index = {'mods': [{'workshop_id': '1', 'package_id': 'dep', 'name': 'Dep'}]}
        local = {'packageId': 'local.target', 'workshopId': None, 'name': 'local'}
        data = {'local.target': metadata('local.target', '<loadBefore><li>dep</li></loadBefore>'), 'dep': metadata('dep')}
        order = cw.resolve_mod_graph(index, ['local.target'], lambda mod: data[mod['packageId']], local=local)
        self.assertEqual([m['packageId'] for m in order], ['local.target', 'dep'])

    def test_versioned_dependencies_override_generic_for_game_version(self):
        index = {'mods': [{'workshop_id': '1', 'package_id': 'a', 'name': 'A'},
                          {'workshop_id': '2', 'package_id': 'b', 'name': 'B'}]}
        data = {'a': metadata('a', '<modDependencies><li><packageId>old</packageId></li></modDependencies>'
                                   '<modDependenciesByVersion><v1.7><li><packageId>b</packageId></li></v1.7></modDependenciesByVersion>'),
                'b': metadata('b')}
        self.assertEqual([x['packageId'] for x in cw.resolve_mod_graph(index, ['a'], lambda m: data[m['packageId']])], ['b', 'a'])

    def test_ambiguous_package_blocks(self):
        index = {'mods': [{'workshop_id': '1', 'package_id': 'a', 'name': 'A'},
                          {'workshop_id': '2', 'package_id': 'A', 'name': 'A2'}]}
        with self.assertRaises(cw.WorkflowError) as caught:
            cw.resolve_mod_graph(index, ['a'], lambda _: metadata('a'))
        self.assertEqual(caught.exception.code, 'dependencyUnresolved')
