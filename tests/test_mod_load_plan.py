"""Synthetic loader selection fixtures; no game files or network."""
import unittest
from xml.etree import ElementTree as ET
from tools import mod_load_plan as p

class LoadPlanTests(unittest.TestCase):
    def test_default_uses_older_version_and_common_and_root(self):
        paths=['About/About.xml','1.5/Defs/Old.xml','1.6/Defs/A.xml','Common/Patches/B.xml','Defs/C.xml']
        self.assertEqual(p.load_folders(paths,None,set()),['1.6','Common',''])
        self.assertTrue(p.select_asset('1.6/Defs/A.xml',['1.6','Common',''],'English'))
        self.assertFalse(p.select_asset('1.5/Defs/Old.xml',['1.6','Common',''],'English'))
        self.assertFalse(p.select_asset('Mods/Foo/Defs/A.xml',[''],'English'))
    def test_load_time_texture_references_are_kept_only_in_effective_folders(self):
        self.assertTrue(p.select_asset('1.6/Textures/Effects/Beam.png',['1.6',''],'English'))
        self.assertFalse(p.select_asset('1.5/Textures/Effects/Beam.png',['1.6',''],'English'))
        self.assertFalse(p.select_asset('1.6/Source/Beam.cs',['1.6',''],'English'))
    def test_default_prefers_exact_then_smallest_future(self):
        self.assertEqual(p.load_folders(['1.6/Defs/A.xml','1.7/Textures/B.png'],None,set()),['1.7',''])
        self.assertEqual(p.load_folders(['1.8/Defs/A.xml','1.9/Defs/A.xml'],None,set()),['1.8',''])
        self.assertEqual(p.load_folders(['0.9/Defs/A.xml'],None,set()),[''])
    def test_custom_folder_replaces_default_and_reverses_precedence(self):
        xml=b'<loadFolders><v1.7><li>/</li><li>Mods/Foo/1.7</li></v1.7></loadFolders>'
        folders=p.load_folders(['Defs/A.xml','Mods/Foo/1.7/Assemblies/A.dll'],xml,set())
        self.assertEqual(folders,['Mods/Foo/1.7',''])
        self.assertTrue(p.select_asset('Mods/Foo/1.7/Assemblies/A.dll',folders,'English'))
    def test_versioned_config_fallback_precedes_default(self):
        xml=b'<loadFolders><default><li>/</li></default><v1.6><li>old</li></v1.6></loadFolders>'
        self.assertEqual(p.load_folders(['old/Defs/A.xml'],xml,set()),['old'])
    def test_conditions_any_all_not_use_complete_request(self):
        xml=b'<loadFolders><v1.7><li>/</li><li IfModActive="a.one,b.two">any</li><li IfModActiveAll="a.one,b.two">all</li><li IfModNotActive="c.three">not</li></v1.7></loadFolders>'
        paths=['Defs/A.xml','any/Defs/A.xml','all/Defs/A.xml','not/Defs/A.xml']
        self.assertEqual(p.load_folders(paths,xml,{'a.one','b.two'}),['not','all','any',''])
        self.assertEqual(p.load_folders(paths,xml,{'c.three'}),[''])
    def test_unknown_malformed_unsafe_missing_or_empty_block(self):
        configs=[b'<loadFolders>',b'<wrong/>',b'<loadFolders><v1.7><li Unhandled="a">/</li></v1.7></loadFolders>',b'<loadFolders><v1.7><li>../escape</li></v1.7></loadFolders>',b'<loadFolders><v1.7><li>missing</li></v1.7></loadFolders>',b'<loadFolders><v1.7><li IfModActive="absent">/</li></v1.7></loadFolders>']
        for xml in configs:
            with self.subTest(xml=xml),self.assertRaises(p.LoadPlanError) as exc:
                p.load_folders(['About/About.xml'],xml,set())
            self.assertTrue(exc.exception.code)
    def test_versioned_dependencies_replace_generic_even_when_empty(self):
        meta=ET.fromstring('<ModMetaData><modDependencies><li><packageId>old.dep</packageId></li></modDependencies><modDependenciesByVersion><v1.7><li><packageId>new.dep</packageId></li></v1.7></modDependenciesByVersion></ModMetaData>')
        self.assertEqual(p.missing_dependencies(meta,{'NEW.DEP'}),[])
        self.assertEqual(p.missing_dependencies(meta,set()),['new.dep'])
        meta.find('modDependenciesByVersion/v1.7').clear()
        self.assertEqual(p.missing_dependencies(meta,set()),[])

    def test_ambiguous_or_text_only_dependencies_block(self):
        for xml in [
            '<ModMetaData><modDependencies/><modDependencies><li><packageId>missing.dep</packageId></li></modDependencies></ModMetaData>',
            '<ModMetaData><modDependenciesByVersion><v1.7/></modDependenciesByVersion><modDependenciesByVersion><v1.7><li><packageId>missing.dep</packageId></li></v1.7></modDependenciesByVersion></ModMetaData>',
            '<ModMetaData><modDependenciesByVersion><v1.7>not-a-list</v1.7></modDependenciesByVersion></ModMetaData>'
        ]:
            with self.subTest(xml=xml):
                with self.assertRaises(p.LoadPlanError) as exc:
                    p.missing_dependencies(ET.fromstring(xml),set())
                self.assertEqual(exc.exception.code,'invalidDependencies')

    def test_utf16_entity_declarations_cannot_bypass_xml_guard(self):
        xml='<!DOCTYPE loadFolders [<!ENTITY root "/">]><loadFolders><v1.7><li>&root;</li></v1.7></loadFolders>'.encode('utf-16')
        with self.assertRaises(p.LoadPlanError):
            p.load_folders(['About/About.xml'],xml,set())

    def test_text_between_folder_entries_blocks(self):
        xml=b'<loadFolders><v1.7>unparsed-folder<li>/</li></v1.7></loadFolders>'
        with self.assertRaises(p.LoadPlanError):
            p.load_folders(['About/About.xml'],xml,set())

    def test_sound_grains_loaded_during_A_are_kept(self):
        self.assertTrue(p.select_asset('1.6/Sounds/Cast.wav',['1.6',''],'English'))
        self.assertFalse(p.select_asset('1.5/Sounds/Cast.wav',['1.6',''],'English'))

    def test_every_audio_extension_the_game_accepts_is_kept(self):
        for ext in ('wav','mp3','ogg','xm','it','mod','s3m','OGG'):
            with self.subTest(ext=ext):
                self.assertTrue(p.select_asset(f'1.6/Sounds/Music.{ext}',['1.6',''],'English'))

    def test_language_archives_are_kept_like_folders(self):
        folders=['1.6','']
        self.assertTrue(p.select_asset('Languages/English.tar',folders,'English'))
        self.assertTrue(p.select_asset('1.6/Languages/Japanese (日本語).tar',folders,'Japanese'))
        self.assertTrue(p.select_asset('Languages/Japanese.tar',folders,'Japanese'))
        self.assertFalse(p.select_asset('Languages/French.tar',folders,'Japanese'))
        self.assertFalse(p.select_asset('1.5/Languages/English.tar',folders,'English'))

    def test_other_content_folders_the_loader_reads_are_kept(self):
        folders=['1.6','']
        self.assertTrue(p.select_asset('1.6/Strings/Names/First.txt',folders,'English'))
        self.assertFalse(p.select_asset('1.6/Strings/Names/First.xml',folders,'English'))
        self.assertTrue(p.select_asset('AssetBundles/shaders_linux',folders,'English'))
        self.assertTrue(p.select_asset('1.6/AssetBundles/shaders_win',folders,'English'))
        self.assertFalse(p.select_asset('AssetBundles/shaders.manifest',folders,'English'))
        self.assertTrue(p.select_asset('1.6/Shaders/Custom/Glow.wgsl',folders,'English'))
        self.assertFalse(p.select_asset('1.5/Shaders/Custom/Glow.wgsl',folders,'English'))
