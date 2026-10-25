from pathlib import Path
import json
import tempfile
import subprocess
import sys
from unittest.mock import patch
import unittest

from tools.mod_preflight import check_profile, load_profile, main


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Windows TEMP can use an 8.3 alias. The CLI resolves profiles, so
        # fixture paths must identify the same canonical directory too.
        self.root = Path(self.temp.name).resolve()
        self.game = self.root / 'Game with spaces'
        self.save = self.root / 'Player data'
        self.config = self.save / 'Config/ModsConfig.xml'
        self.config.parent.mkdir(parents=True)
        self.mod('Core', 'ludeon.rimworld', official=True)
        self.mod('Example', 'test.example')
        self.active('ludeon.rimworld', 'test.example')
        (self.game / 'RimWorld.exe').write_bytes(b'fixture executable, not run')
        (self.game / 'RimWorld').write_bytes(b'fixture executable, not run')
        self.profile = {'schemaVersion': 1, 'gameDir': str(self.game),
                        'saveDataDir': str(self.save), 'modRoots': [], 'gameVersion': '1.7'}

    def mod(self, folder, package, extra='', official=False):
        root = self.game / ('Data' if official else 'Mods') / folder
        (root / 'About').mkdir(parents=True)
        (root / 'About/About.xml').write_text(
            f'<ModMetaData><packageId>{package}</packageId>'
            f'<supportedVersions><li>1.7</li></supportedVersions>{extra}</ModMetaData>', encoding='utf-8')
        (root / 'Defs').mkdir()
        (root / 'Defs/a.xml').write_text('<Defs><ThingDef/></Defs>', encoding='utf-8')
        return root

    def active(self, *ids):
        body = ''.join(f'<li>{p}</li>' for p in ids)
        self.config.write_text(f'<ModsConfigData><version>1.7.4985</version><activeMods>{body}</activeMods></ModsConfigData>', encoding='utf-8')

    def codes(self, report):
        return {d['code'] for d in report['diagnostics']}

    def test_same_profile_checks_without_game_execution_or_input_changes(self):
        before = self.config.read_bytes()
        r = check_profile(self.profile)
        self.assertEqual(r['auditStatus'], 'passed')
        self.assertEqual(r['gameVerification'], 'notRun')
        self.assertEqual(r['activeMods'], ['ludeon.rimworld', 'test.example'])
        self.assertEqual(r['statistics']['xmlFilesChecked'], 2)
        self.assertEqual(self.config.read_bytes(), before)

    def test_missing_and_duplicate_active_mods_block(self):
        for ids in [('ludeon.rimworld', 'missing'), ('ludeon.rimworld', 'test.example', 'test.example')]:
            with self.subTest(ids=ids):
                self.active(*ids)
                self.assertEqual(check_profile(self.profile)['auditStatus'], 'failed')

    def test_core_is_required_first(self):
        self.active('test.example', 'ludeon.rimworld')
        self.assertIn('coreOrder', self.codes(check_profile(self.profile)))

    def test_ambiguous_package_sources_are_not_silently_selected(self):
        self.mod('Duplicate', 'test.example')
        self.assertIn('ambiguousPackage', self.codes(check_profile(self.profile)))

    def test_inactive_broken_xml_is_not_checked(self):
        other = self.mod('Inactive', 'test.inactive')
        (other / 'Defs/a.xml').write_text('<broken>')
        self.assertEqual(check_profile(self.profile)['auditStatus'], 'passed')

    def test_missing_dependency_and_conflict(self):
        about = self.game / 'Mods/Example/About/About.xml'
        for extra, code in [('<modDependencies><li><packageId>missing</packageId></li></modDependencies>', 'dependencyMissing'),
                            ('<incompatibleWith><li>ludeon.rimworld</li></incompatibleWith>', 'incompatible')]:
            with self.subTest(code=code):
                about.write_text(f'<ModMetaData><packageId>test.example</packageId>{extra}</ModMetaData>')
                self.assertIn(code, self.codes(check_profile(self.profile)))

    def test_force_order_is_checked_without_reordering(self):
        mod = self.mod('Ordered', 'test.ordered', '<forceLoadBefore><li>test.example</li></forceLoadBefore>')
        self.active('ludeon.rimworld', 'test.example', 'test.ordered')
        self.assertIn('loadOrder', self.codes(check_profile(self.profile)))
        self.active('ludeon.rimworld', 'test.ordered', 'test.example')
        self.assertEqual(check_profile(self.profile)['auditStatus'], 'passed')

    def test_version_mismatch_and_invalid_xml_are_errors(self):
        about = self.game / 'Mods/Example/About/About.xml'
        original = about.read_text()
        about.write_text(original.replace('1.7', '1.6'))
        self.assertIn('versionMismatch', self.codes(check_profile(self.profile)))
        about.write_text(original)
        (about.parent.parent / 'Defs/a.xml').write_text('<broken>')
        self.assertIn('xmlSyntax', self.codes(check_profile(self.profile)))

    def test_old_version_folder_is_not_mistaken_for_selected_version(self):
        root = self.game / 'Mods/Example'
        for version, text in [('1.6', '<broken>'), ('1.7', '<Defs/>')]:
            (root / version / 'Defs').mkdir(parents=True)
            (root / version / 'Defs/v.xml').write_text(text)
        self.assertEqual(check_profile(self.profile)['auditStatus'], 'passed')

    def test_loadfolders_paths_and_unknown_conditions_do_not_pass(self):
        path = self.game / 'Mods/Example/LoadFolders.xml'
        for body in ['<v1.7><li>../outside</li></v1.7>',
                     '<v1.7><li UnknownCondition="x">/</li></v1.7>']:
            with self.subTest(body=body):
                path.write_text('<loadFolders>' + body + '</loadFolders>')
                self.assertNotEqual(check_profile(self.profile)['auditStatus'], 'passed')

    def test_explicit_loadfolders_only_checks_selected_content(self):
        root = self.game / 'Mods/Example'
        (root / 'Defs/a.xml').write_text('<broken>')
        (root / 'Selected/Defs').mkdir(parents=True)
        (root / 'Selected/Defs/a.xml').write_text('<Defs/>')
        (root / 'LoadFolders.xml').write_text('<loadFolders><v1.7><li>Selected</li></v1.7></loadFolders>')
        self.assertEqual(check_profile(self.profile)['auditStatus'], 'passed')

    def test_steam_suffix_resolves_only_unambiguous_source(self):
        self.active('ludeon.rimworld', 'test.example_steam')
        self.assertEqual(check_profile(self.profile)['auditStatus'], 'passed')
        self.mod('Second', 'test.example')
        self.assertNotEqual(check_profile(self.profile)['auditStatus'], 'passed')

    def test_profile_relative_paths_are_resolved_against_profile_file(self):
        path = self.root / 'profile.json'
        profile = dict(self.profile, gameDir=self.game.name, saveDataDir=self.save.name)
        path.write_text(json.dumps(profile))
        r = check_profile(load_profile(path))
        self.assertEqual(r['auditStatus'], 'passed')

    def test_check_does_not_require_the_official_executable(self):
        (self.game / 'RimWorld.exe').unlink()
        (self.game / 'RimWorld').unlink()
        self.assertEqual(check_profile(self.profile)['auditStatus'], 'passed')

    def test_fingerprint_changes_after_config_xml_dll_profile_or_exe_change(self):
        for kind in ['config', 'xml', 'dll', 'profile', 'exe']:
            with self.subTest(kind=kind):
                self.setUp()
                report = check_profile(self.profile)
                if kind == 'config':self.active('ludeon.rimworld')
                elif kind == 'xml':(self.game / 'Mods/Example/Defs/a.xml').write_text('<Defs><Other/></Defs>')
                elif kind == 'dll':
                    folder = self.game / 'Mods/Example/Assemblies';folder.mkdir();(folder/'x.dll').write_bytes(b'not loaded')
                elif kind == 'profile':self.profile['modRoots'] = [str(self.root)]
                else:(self.game / 'RimWorld.exe').write_bytes(b'changed')
                self.assertNotEqual(check_profile(self.profile)['fingerprint'], report['fingerprint'])

    def test_unknown_version_fallback_does_not_report_success(self):
        path = self.game / 'Mods/Example/LoadFolders.xml'
        path.write_text('<loadFolders><v1.6><li>Old</li></v1.6><default><li>/</li></default></loadFolders>')
        self.assertEqual(check_profile(self.profile)['auditStatus'], 'incomplete')

    def cli(self, *args):
        return subprocess.run([sys.executable, 'tools/mod_preflight.py', *map(str, args)],
                              capture_output=True, text=True, check=False)

    def save_profile(self):
        path = self.root / 'profile.json'
        path.write_text(json.dumps(self.profile), encoding='utf-8')
        return path

    def test_cli_check_writes_a_static_only_report(self):
        profile = self.save_profile();report = self.root / 'result.json'
        out = self.cli('check', '--profile', profile, '--output', report)
        self.assertEqual(out.returncode, 0, out.stderr)
        result = json.loads(report.read_text())
        self.assertEqual(result['recordType'], 'modPreflight')
        self.assertEqual(result['gameVerification'], 'notRun')

    def test_removed_play_command_reports_migration_error(self):
        profile = self.save_profile();report = self.root / 'result.json'
        self.cli('check', '--profile', profile, '--output', report)
        for extra in ([], ['--dry-run'], ['--acknowledge-static-only']):
            with self.subTest(extra=extra):
                out = self.cli('play', '--profile', profile, '--report', report, *extra)
                self.assertEqual(out.returncode, 1)
                self.assertIn('never starts the game', json.loads(out.stdout)['error'])

    def test_no_entry_point_spawns_a_process(self):
        profile = self.save_profile();report = self.root / 'result.json'
        spawn = AssertionError('a process was spawned')
        with patch('subprocess.Popen', side_effect=spawn), patch('os.system', side_effect=spawn), \
                patch('os.execv', side_effect=spawn), patch('builtins.print'):
            self.assertEqual(main(['check', '--profile', str(profile), '--output', str(report)]), 0)
            self.assertEqual(main(['play', '--profile', str(profile), '--report', str(report)]), 1)

    def test_reports_cannot_overwrite_game_data_or_profile(self):
        profile = self.save_profile()
        for path in (profile, self.config, self.game / 'Mods/Example/Defs/a.xml'):
            with self.subTest(path=path):
                before = path.read_bytes()
                out = self.cli('check', '--profile', profile, '--output', path)
                self.assertEqual(out.returncode, 1)
                self.assertEqual(path.read_bytes(), before)

    def test_invalid_profile_returns_json_failure(self):
        profile = self.root / 'bad.json';profile.write_text('[]')
        out = self.cli('check', '--profile', profile)
        self.assertEqual(out.returncode, 1)
        self.assertEqual(json.loads(out.stdout)['auditStatus'], 'failed')

    def test_unreadable_active_directory_cannot_silently_pass(self):
        import os
        original = os.scandir
        blocked = self.game / 'Mods/Example/Defs'
        def scandir(path):
            if Path(path) == blocked:
                raise PermissionError('simulated unreadable active directory')
            return original(path)
        with patch('tools.mod_preflight.os.scandir', side_effect=scandir):
            self.assertNotEqual(check_profile(self.profile)['auditStatus'], 'passed')

    def test_version_directory_symlink_cannot_escape_mod_root(self):
        root = self.game / 'Mods/Example'
        outside = self.root / 'outside';(outside/'Defs').mkdir(parents=True)
        (outside/'Defs/a.xml').write_text('<Defs/>')
        try:
            (root/'1.7').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('filesystem symlinks unavailable')
        self.assertNotEqual(check_profile(self.profile)['auditStatus'], 'passed')

    def test_output_parent_is_created_without_touching_game_data(self):
        profile = self.save_profile()
        report = self.root / 'new-results/check.json'
        out = self.cli('check', '--profile', profile, '--output', report)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(report.read_text())['auditStatus'], 'passed')

    def test_output_cannot_escape_protection_through_directory_link(self):
        from tools.mod_preflight import write_json
        outside = self.root / 'outside';outside.mkdir()
        data = outside / 'input.xml';data.write_text('<original/>')
        link = self.game / 'linked'
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('filesystem symlinks unavailable')
        with self.assertRaises(ValueError):
            write_json(link/'input.xml', {'x':1}, self.profile)
        self.assertEqual(data.read_text(), '<original/>')

    def test_desktop_result_distinguishes_preflight_from_game_verification(self):
        from tools.preflight_gui import format_result
        text = format_result(check_profile(self.profile))
        self.assertIn('事前検査：通過', text)
        self.assertIn('ゲーム実行検証：未実施', text)

    @unittest.skipUnless(sys.platform == 'win32', 'native Windows Tk window smoke test')
    def test_windows_desktop_window_can_be_created(self):
        from tools.preflight_gui import create_window
        window = create_window()
        try:
            window.update_idletasks()
            self.assertTrue(window.winfo_children())
        finally:
            window.destroy()

    def test_desktop_has_no_game_launch_path(self):
        source = Path('tools/preflight_gui.py').read_text(encoding='utf-8')
        for forbidden in ('subprocess', 'launch', 'Popen', 'startfile', 'ゲームを起動する'):
            self.assertNotIn(forbidden, source)


if __name__ == '__main__':
    unittest.main()
