"""Game-free tests of the GUI launcher (tools/gui_host.py).

A fake GUI (a small Python script) stands in for RimWorldValidationGui: it reports
what it was given into the results folder, so these tests run in public CI.
"""
from pathlib import Path
import json
import os
import stat
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

from tools import gui_host
from tools import validation_host as vh
from tests.test_validation_host import HOST_PLATFORM, OTHER_PLATFORM, WINDOWS, Fixture, pid_alive, wait_until_gone

FAKE_GUI = textwrap.dedent('''\
    #!/usr/bin/env python3
    # Fake GUI for launcher tests. Behaviour is chosen by the request's script.
    import json, os, subprocess, sys
    request_path = sys.argv[sys.argv.index('--gui-request') + 1]
    request = json.load(open(request_path, encoding='utf-8'))
    host, userdata = request['hostDir'], request['userDataDir']
    report = {
        'argv': sys.argv[1:], 'cwd': os.getcwd(), 'env': dict(os.environ), 'request': request,
        'host': sorted(os.listdir(host)), 'data': sorted(os.listdir(os.path.join(host, 'Data'))),
        'mods': sorted(os.listdir(os.path.join(host, 'Mods'))),
        'modsConfig': open(os.path.join(userdata, 'Config', 'ModsConfig.xml'), encoding='utf-8').read(),
        'prefs': open(os.path.join(userdata, 'Config', 'Prefs.xml'), encoding='utf-8').read(),
        'deps': json.load(open(os.path.join(host, 'RimWorldValidationGui.deps.json'), encoding='utf-8')),
    }
    steps = request.get('script') or []
    if {'fake': 'leaveChild'} in steps:
        # A validation still running when the window closes.
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
        report['childPid'] = child.pid
    with open(os.path.join(request['resultsDir'], 'fake-gui.json'), 'w', encoding='utf-8') as stream:
        json.dump(report, stream)
    sys.exit(7 if {'fake': 'exit7'} in steps else 0)
''')


class GuiCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.fx = Fixture(self.root, HOST_PLATFORM)
        self.fx.prepare()
        self.gui = self.root / 'gui-bin'
        self.gui.mkdir()
        exe = self.gui / (gui_host.GUI_NAME + ('.exe' if WINDOWS else ''))
        exe.write_text(FAKE_GUI, encoding='utf-8')
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
        (self.gui / f'{gui_host.GUI_NAME}.dll').write_bytes(b'fake gui assembly')
        (self.gui / 'RimWorldValidation.Gui.Model.dll').write_bytes(b'fake model assembly')
        self.results = self.root / 'results'
        if WINDOWS:
            # The fake GUI is a Python script: Windows cannot execute it by its shebang.
            patcher = mock.patch.object(gui_host, 'gui_command', lambda host, request: [
                sys.executable, str(host / (gui_host.GUI_NAME + '.exe')), '--gui-request', str(request)])
            patcher.start()
            self.addCleanup(patcher.stop)

    def settings(self, **fields):
        return {'snapshot': str(self.fx.snapshot), 'results': str(self.results), 'mods': [str(self.fx.mods)],
                'modsConfig': None, 'memoryMiB': 4096, **fields}

    def launch(self, script=None, **kwargs):
        options = {'gui_dir': self.gui, 'worker_dir': self.fx.worker, 'adapters': self.fx.adapters, 'log': lambda *_: None}
        options.update(kwargs)
        process = gui_host.launch(self.settings(), script=script, **options)
        return process, json.loads((self.results / 'fake-gui.json').read_text(encoding='utf-8'))


class GuiDirTests(GuiCase):
    def test_gui_dir_links_game_and_mods_and_writes_private_config(self):
        self.fx.mod('alpha')
        self.fx.mod('beta')
        process, report = self.launch(script=[{'tab': 'mods'}])
        self.assertEqual(process['exitCode'], 0)
        self.assertIsNone(process['killedFor'])
        self.assertEqual(report['data'], ['Core', 'Royalty'])
        self.assertEqual(report['mods'], ['0-alpha', '1-beta'])
        self.assertEqual(report['request']['modsMap'], {'0-alpha': str((self.fx.mods / 'alpha').resolve()),
                                                        '1-beta': str((self.fx.mods / 'beta').resolve())})
        self.assertEqual(report['request']['script'], [{'tab': 'mods'}])
        self.assertEqual(report['request']['resultsDir'], str(self.results))
        self.assertEqual(report['request']['recordType'], 'rwmtGuiRequest')
        # The official executable is never linked; the GUI is the application.
        self.assertNotIn('RimWorld', report['host'])
        self.assertNotIn('RimWorld.exe', report['host'])
        self.assertIn(f'{gui_host.GUI_NAME}.dll', report['host'])
        self.assertIn('RimWorldValidation.Gui.Model.dll', report['host'])
        self.assertIn('Other.dll', report['host'])
        # Only official content is active; the user's mods are chosen in the GUI.
        self.assertIn('<li>ludeon.rimworld</li><li>ludeon.rimworld.royalty</li></activeMods>', report['modsConfig'])
        self.assertNotIn('test.alpha', report['modsConfig'])
        self.assertIn('<devMode>false</devMode>', report['prefs'])
        self.assertIn('<langFolderName>Japanese (日本語)</langFolderName>', report['prefs'])
        target = report['deps']['runtimeTarget']['name']
        root = report['deps']['targets'][target][f'{gui_host.GUI_NAME}/{vh.TOOL_VERSION}']
        self.assertEqual(set(root['runtime']), {f'{gui_host.GUI_NAME}.dll', 'RimWorldValidation.Gui.Model.dll', 'RimWorld.dll'})
        self.assertNotIn('RimWorld/1.0.0', report['deps']['libraries'])
        self.assertEqual(Path(report['cwd']).resolve(), (self.results / gui_host.GUI_SESSION / 'host').resolve())
        # The session is removed afterwards, and the snapshot it linked to is intact.
        self.assertFalse((self.results / gui_host.GUI_SESSION).exists())
        vh.load_snapshot(self.fx.snapshot, full=True)

    def test_duplicate_package_ids_keep_the_first_root(self):
        first = self.root / 'first'
        second = self.root / 'second'
        Fixture.about(first / 'Same', 'Test.Same')
        Fixture.about(second / 'Same2', 'test.same')
        Fixture.about(second / 'Other', 'test.other')
        (second / 'NotAMod').mkdir()
        found, skipped = gui_host.discover_mod_folders([first, second])
        self.assertEqual([(m['packageId'], Path(m['path']).name) for m in found],
                         [('test.same', 'Same'), ('test.other', 'Other')])
        self.assertEqual(len(skipped), 1)
        self.assertEqual(Path(skipped[0]['path']).name, 'Same2')
        self.assertIn('same packageId test.same', skipped[0]['reason'])

    def test_broken_about_is_skipped_not_fatal(self):
        root = self.root / 'roots'
        (root / 'Broken' / 'About').mkdir(parents=True)
        (root / 'Broken' / 'About' / 'About.xml').write_text('<ModMetaData><packageId>', encoding='utf-8')
        Fixture.about(root / 'Good', 'test.good')
        found, skipped = gui_host.discover_mod_folders([root])
        self.assertEqual([m['packageId'] for m in found], ['test.good'])
        self.assertEqual(Path(skipped[0]['path']).name, 'Broken')

    def test_missing_root_is_skipped_not_fatal(self):
        Fixture.about(self.root / 'present' / 'Good', 'test.good')
        found, skipped = gui_host.discover_mod_folders([self.root / 'gone', self.root / 'present'])
        self.assertEqual([m['packageId'] for m in found], ['test.good'])
        self.assertEqual(skipped, [{'path': str(self.root / 'gone'), 'reason': 'mod folder root not found'}])

    def test_default_roots_follow_the_steam_layout(self):
        source = self.root / 'Steam' / 'steamapps' / 'common' / 'RimWorld'
        (source / 'Mods').mkdir(parents=True)
        workshop = self.root / 'Steam' / 'steamapps' / 'workshop' / 'content' / '294100'
        workshop.mkdir(parents=True)
        self.assertEqual(gui_host.default_mod_roots({'sourcePath': str(source)}), [source / 'Mods', workshop])
        # Outside a Steam library only the install's Mods folder, and only when it exists.
        self.assertEqual(gui_host.default_mod_roots({'sourcePath': str(self.root / 'nowhere')}), [])

    def test_environment_keeps_only_display_variables(self):
        values = {'DISPLAY': ':42', 'VK_ICD_FILENAMES': '/icd.json', 'RWMT_SECRET_FOR_TEST': 'must not leak'}
        with mock.patch.dict(os.environ, values):
            _, report = self.launch()
        env = report['env']
        self.assertEqual(env.get('DISPLAY'), ':42')
        self.assertEqual(env.get('VK_ICD_FILENAMES'), '/icd.json')
        self.assertNotIn('RWMT_SECRET_FOR_TEST', env)
        self.assertNotIn('DOTNET_GCHeapHardLimit', env)
        home = env.get('USERPROFILE' if WINDOWS else 'HOME')
        self.assertTrue(Path(home).is_relative_to(self.results / gui_host.GUI_SESSION))


class LaunchTests(GuiCase):
    def test_launch_runs_the_gui_and_cleans_up(self):
        self.fx.mod('alpha')
        process, _ = self.launch(script=[{'fake': 'exit7'}])
        self.assertEqual(process['exitCode'], 7)
        self.assertFalse(process['strayProcessesKilled'])
        self.assertFalse((self.results / gui_host.GUI_SESSION).exists())
        self.assertTrue((self.fx.mods / 'alpha' / 'About' / 'About.xml').is_file())

    def test_keep_run_dir_leaves_the_session_for_inspection(self):
        process, _ = self.launch(keep_run_dir=True)
        self.assertEqual(Path(process['runDir']), self.results / gui_host.GUI_SESSION)
        self.assertTrue((self.results / gui_host.GUI_SESSION / 'gui-request.json').is_file())

    def test_a_crashed_session_is_replaced(self):
        stale = self.results / gui_host.GUI_SESSION / 'host'
        stale.mkdir(parents=True)
        (stale / 'leftover.txt').write_text('x', encoding='utf-8')
        process, report = self.launch()
        self.assertEqual(process['exitCode'], 0)
        self.assertNotIn('leftover.txt', report['host'])

    def test_closing_the_gui_stops_its_children(self):
        process, report = self.launch(script=[{'fake': 'leaveChild'}])
        self.assertTrue(process['strayProcessesKilled'])
        self.assertTrue(wait_until_gone(report['childPid']))
        self.assertFalse(pid_alive(report['childPid']))

    def test_missing_gui_build_is_reported(self):
        empty = self.root / 'empty'
        empty.mkdir()
        with self.assertRaises(vh.Blocked) as caught:
            gui_host.launch(self.settings(), gui_dir=empty, worker_dir=self.fx.worker, adapters=self.fx.adapters,
                            log=lambda *_: None)
        self.assertEqual(caught.exception.code, 'guiMissing')

    def test_snapshot_of_another_platform_is_refused(self):
        with self.assertRaises(vh.Blocked) as caught:
            gui_host.launch(self.settings(), gui_dir=self.gui, worker_dir=self.fx.worker, adapters=self.fx.adapters,
                            platform=OTHER_PLATFORM, log=lambda *_: None)
        self.assertEqual(caught.exception.code, 'platformMismatch')

    def test_unknown_build_needs_the_explicit_flag(self):
        with self.assertRaises(vh.Blocked) as caught:
            gui_host.launch(self.settings(), gui_dir=self.gui, worker_dir=self.fx.worker, adapters={},
                            log=lambda *_: None)
        self.assertEqual(caught.exception.code, 'unknownBuild')
        process, _ = self.launch(adapters={}, allow_unknown_build=True)
        self.assertEqual(process['exitCode'], 0)


class CommandLineTests(GuiCase):
    def test_setup_then_launch_reads_the_saved_settings(self):
        path = self.root / 'settings.json'
        code = gui_host.main(['setup', '--snapshot', str(self.fx.snapshot), '--results', str(self.results),
                              '--mods', str(self.fx.mods), '--settings', str(path)])
        self.assertEqual(code, 0)
        saved = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(saved['mods'], [str(self.fx.mods.resolve())])
        self.assertEqual(saved['memoryMiB'], gui_host.DEFAULT_MEMORY_MIB)

    def test_launch_without_setup_is_blocked(self):
        code = gui_host.main(['launch', '--settings', str(self.root / 'missing.json')])
        self.assertEqual(code, vh.EXIT_CODES['blocked'])


if __name__ == '__main__':
    unittest.main()
