"""Synthetic R2 boundary fixtures for metadata-first loader planning."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from tools import codex_workflow as c

class FetchPlanTests(unittest.TestCase):
    def run_fetch(self, extra, about=None, official=None, stale_directory=None):
        directory=tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        root=Path(directory.name);archive=root/'index.zip'
        with ZipFile(archive,'w') as z:
            z.writestr('mods.json',json.dumps({'schema_version':1,'mods':[{'name':'Example','workshop_id':'123','package_id':'author.example'}]}))
        files={'About/About.xml':about or b'<ModMetaData><packageId>author.example</packageId></ModMetaData>',**extra}
        if stale_directory:
            (root/"private/mods/123"/stale_directory).mkdir(parents=True)
        self.pulled=[]
        outer=self
        class R2:
            def list_prefix(self,prefix):return [{'key':prefix+k,'size':len(v)} for k,v in files.items()]
            def get(self,key,dest,size,refresh=False):
                outer.pulled.append(key.split('/',2)[2]);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(files[key.split('/',2)[2]]);return 'downloaded'
        args=SimpleNamespace(private_root=root/'private',index_zip=str(archive),aws='aws',refresh=False,target='Example',dependency=[],scope='validation',language='English',official=official or ['Core'])
        with patch.object(c,'r2_client',return_value=R2()):return c.fetch_mods(args)
    def test_default_downloads_fallback_version(self):
        result=self.run_fetch({'1.6/Defs/A.xml':b'<Defs/>','1.5/Defs/B.xml':b'<Defs/>'})
        self.assertIn('1.6/Defs/A.xml',self.pulled)
        self.assertNotIn('1.5/Defs/B.xml',self.pulled)
        self.assertEqual(result['fetched'][0]['loadFolders'],['1.6',''])
        request=json.loads(Path(result['request']).read_text())
        self.assertEqual(request['mods'][0]['expectedLoadFolders'],['1.6',''])
    def test_custom_folders_and_dlc_condition(self):
        self.run_fetch({'LoadFolders.xml':b'<loadFolders><v1.7><li>/</li><li IfModActive="ludeon.rimworld.royalty">Mods/Foo</li></v1.7></loadFolders>','Mods/Foo/Defs/A.xml':b'<Defs/>'},official=['Core','Royalty'])
        self.assertIn('Mods/Foo/Defs/A.xml',self.pulled)
        self.assertLess(self.pulled.index('LoadFolders.xml'),self.pulled.index('Mods/Foo/Defs/A.xml'))
    def test_bad_loadfolders_blocks_before_payload(self):
        with self.assertRaises(c.WorkflowError) as exc:
            self.run_fetch({'LoadFolders.xml':b'<broken','1.7/Assemblies/A.dll':b'x'})
        self.assertEqual(exc.exception.code,'invalidMetadataXml')
        self.assertNotIn('1.7/Assemblies/A.dll',self.pulled)
    def test_missing_dependency_blocks_before_payload(self):
        with self.assertRaises(c.WorkflowError) as exc:
            self.run_fetch({'1.7/Assemblies/A.dll':b'x'},about=b'<ModMetaData><packageId>author.example</packageId><modDependencies><li><packageId>missing.dep</packageId></li></modDependencies></ModMetaData>')
        self.assertEqual(exc.exception.code,'missingDependencies')
        self.assertNotIn('1.7/Assemblies/A.dll',self.pulled)

    def test_stale_local_version_directory_blocks_before_payload(self):
        with self.assertRaises(c.WorkflowError) as exc:
            self.run_fetch({'1.6/Assemblies/A.dll':b'x'},stale_directory='1.7')
        self.assertEqual(exc.exception.code,'unexpectedCachedModInputs')
        self.assertNotIn('1.6/Assemblies/A.dll',self.pulled)

    def test_selected_folder_is_materialized_without_loader_files(self):
        result=self.run_fetch({'1.7/Source/A.cs':b'x','1.6/Defs/A.xml':b'<Defs/>'})
        request=json.loads(Path(result['request']).read_text())
        mod=Path(request['mods'][0]['path'])
        self.assertTrue((mod/'1.7').is_dir())
        self.assertFalse((mod/'1.6').exists())
