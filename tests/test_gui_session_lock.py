"""The GUI session has one owner, including while rebuilding or cleaning it."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import textwrap
import time
import unittest
from unittest import mock

from tools import gui_host
from tools import validation_host as vh
from tests.test_gui_host import GuiCase, WINDOWS
from tests.test_validation_host import pid_alive, wait_until_gone


FAKE_GUI = textwrap.dedent('''\
    #!/usr/bin/env python3
    import json, os, pathlib, subprocess, sys, time
    request = json.load(open(sys.argv[sys.argv.index('--gui-request') + 1], encoding='utf-8'))
    results = pathlib.Path(request['resultsDir'])
    if request.get('script') in (['wait'], ['tree']):
        pids = {'supervisor': os.getppid(), 'gui': os.getpid()}
        if request['script'] == ['tree']:
            worker_file = results / 'worker.pid'
            lock_stat = (results / '.gui-session.lock').stat()
            lock_fd = next(int(entry.name) for entry in pathlib.Path('/proc/self/fd').iterdir()
                if entry.exists() and entry.stat().st_ino == lock_stat.st_ino and entry.stat().st_dev == lock_stat.st_dev)
            controller_code = ("import pathlib, subprocess, sys, time; "
                "sys.path.insert(0, sys.argv[2]); from tools import validation_host as vh; "
                "fds = getattr(vh, '_gui_session_lock_fds', lambda: ())(); "
                "worker = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'], start_new_session=True, pass_fds=fds); "
                "target = pathlib.Path(sys.argv[1]); tmp = target.with_suffix('.tmp'); "
                "tmp.write_text(str(worker.pid)); tmp.replace(target); time.sleep(600)")
            env = dict(os.environ, RWMT_GUI_LOCK_FD=str(lock_fd))
            controller = subprocess.Popen([sys.executable, '-c', controller_code, str(worker_file),
                str(pathlib.Path(request['controller']).parents[1])], env=env, pass_fds=(lock_fd,))
            while not worker_file.exists():
                time.sleep(0.02)
            pids.update(controller=controller.pid, worker=int(worker_file.read_text()))
        (results / 'ready.tmp').write_text(json.dumps(pids), encoding='utf-8')
        (results / 'ready.tmp').replace(results / 'ready')
        while not (results / 'stop').exists():
            time.sleep(0.02)
''')

LAUNCH = textwrap.dedent('''\
    import json, os, sys
    from tools import gui_host
    if os.name == 'nt':
        gui_host.gui_command = lambda host, request: [sys.executable, str(host / 'RimWorldValidationGui.exe'), '--gui-request', str(request)]
    result = gui_host.launch(json.loads(sys.argv[1]), gui_dir=sys.argv[2], worker_dir=sys.argv[3],
                             allow_unknown_build=True, script=[sys.argv[4]], log=lambda *_: None)
    print(json.dumps(result))
    sys.exit(0 if result['exitCode'] == 0 else 1)
''')


class SessionLockTests(GuiCase):
    def setUp(self):
        super().setUp()
        executable = self.gui / (gui_host.GUI_NAME + ('.exe' if WINDOWS else ''))
        executable.write_text(FAKE_GUI, encoding='utf-8')

    def start_launcher(self, script='wait'):
        process = subprocess.Popen([sys.executable, '-c', LAUNCH, json.dumps(self.settings()),
                                    str(self.gui), str(self.fx.worker), script],
                                   cwd=gui_host.REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.stop_launcher, process)
        deadline = time.monotonic() + 15
        while not (self.results / 'ready').exists():
            if process.poll() is not None:
                self.fail(f'launcher exited early: {process.communicate()}')
            if time.monotonic() >= deadline:
                self.fail('launcher did not become ready')
            time.sleep(0.02)
        return process

    def stop_launcher(self, process):
        self.results.mkdir(parents=True, exist_ok=True)
        (self.results / 'stop').touch()
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()

    def test_second_launcher_does_not_remove_the_running_session(self):
        process = self.start_launcher()
        request = self.results / '.gui-session' / 'gui-request.json'
        original = request.read_bytes()
        with self.assertRaises(vh.Blocked) as caught:
            gui_host.launch(self.settings(), gui_dir=self.gui, worker_dir=self.fx.worker,
                            adapters=self.fx.adapters, log=lambda *_: None)
        self.assertEqual(caught.exception.code, 'guiSessionBusy')
        self.assertIsNone(process.poll())
        self.assertEqual(request.read_bytes(), original)

    def test_build_failure_releases_session_for_next_launch(self):
        with mock.patch.object(gui_host, 'build_gui_dir', side_effect=RuntimeError('build failed')):
            with self.assertRaisesRegex(RuntimeError, 'build failed'):
                gui_host.launch(self.settings(), gui_dir=self.gui, worker_dir=self.fx.worker,
                                adapters=self.fx.adapters, log=lambda *_: None)
        process = gui_host.launch(self.settings(), gui_dir=self.gui, worker_dir=self.fx.worker,
                                  adapters=self.fx.adapters, log=lambda *_: None)
        self.assertEqual(process['exitCode'], 0)

    def test_gui_start_failure_releases_session_for_next_launch(self):
        with mock.patch.object(gui_host, 'run_gui', side_effect=OSError('start failed')):
            with self.assertRaisesRegex(OSError, 'start failed'):
                gui_host.launch(self.settings(), gui_dir=self.gui, worker_dir=self.fx.worker,
                                adapters=self.fx.adapters, log=lambda *_: None)
        process = gui_host.launch(self.settings(), gui_dir=self.gui, worker_dir=self.fx.worker,
                                  adapters=self.fx.adapters, log=lambda *_: None)
        self.assertEqual(process['exitCode'], 0)

    def test_launcher_crash_keeps_live_gui_safe_then_releases_session(self):
        process = self.start_launcher()
        process.kill()
        process.communicate(timeout=10)
        if not WINDOWS:
            # The GUI outlives an uncatchable launcher death on Unix. It must
            # retain the lock until it exits, even though its parent is gone.
            with self.assertRaises(vh.Blocked) as caught:
                gui_host.launch(self.settings(), gui_dir=self.gui, worker_dir=self.fx.worker,
                                adapters=self.fx.adapters, log=lambda *_: None)
            self.assertEqual(caught.exception.code, 'guiSessionBusy')
        (self.results / 'stop').touch()
        deadline = time.monotonic() + 15
        while True:
            try:
                result = gui_host.launch(self.settings(), gui_dir=self.gui, worker_dir=self.fx.worker,
                                         adapters=self.fx.adapters, log=lambda *_: None)
                break
            except vh.Blocked as error:
                if error.code != 'guiSessionBusy' or time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
        self.assertEqual(result['exitCode'], 0)

    @unittest.skipIf(WINDOWS, 'Linux supervisor is not used on Windows')
    def test_supervisor_crash_stops_detached_worker_before_session_cleanup(self):
        process = self.start_launcher('tree')
        pids = json.loads((self.results / 'ready').read_text(encoding='utf-8'))
        def kill_remaining():
            for name in ('worker', 'controller', 'gui'):
                try:
                    os.kill(pids[name], signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.addCleanup(kill_remaining)
        for name in ('worker', 'controller', 'gui'):
            self.assertTrue(pid_alive(pids[name]), f'{name} was not running')
        os.kill(pids['supervisor'], signal.SIGKILL)
        stdout, stderr = process.communicate(timeout=10)
        self.assertNotEqual(process.returncode, 0, stderr)
        result = json.loads(stdout)
        self.assertNotEqual(result['exitCode'], 0)
        for name in ('worker', 'controller', 'gui'):
            self.assertFalse(pid_alive(pids[name]), f'{name} survived supervisor crash')
        self.assertFalse((self.results / '.gui-session').exists())

    @unittest.skipIf(WINDOWS, 'Linux guardian is not used on Windows')
    def test_guardian_crash_keeps_session_busy_while_detached_worker_lives(self):
        process = self.start_launcher('tree')
        pids = json.loads((self.results / 'ready').read_text(encoding='utf-8'))
        def kill_remaining():
            for name in ('worker', 'controller', 'gui', 'supervisor'):
                try:
                    os.kill(pids[name], signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.addCleanup(kill_remaining)
        guardian_stat = Path(f"/proc/{pids['supervisor']}/stat").read_text()
        guardian_pid = int(guardian_stat.rsplit(')', 1)[1].split()[1])
        os.kill(guardian_pid, signal.SIGKILL)
        stdout, stderr = process.communicate(timeout=10)
        self.assertNotEqual(process.returncode, 0, stderr)
        self.assertTrue(json.loads(stdout).get('cleanupError'))
        for name in ('supervisor', 'gui', 'controller'):
            os.kill(pids[name], signal.SIGKILL)
        for name in ('supervisor', 'gui', 'controller'):
            self.assertTrue(wait_until_gone(pids[name]), name)
        self.assertTrue(pid_alive(pids['worker']))
        with self.assertRaises(vh.Blocked) as caught:
            gui_host.launch(self.settings(), gui_dir=self.gui, worker_dir=self.fx.worker,
                            adapters=self.fx.adapters, log=lambda *_: None)
        self.assertEqual(caught.exception.code, 'guiSessionBusy')
        os.kill(pids['worker'], signal.SIGKILL)
        self.assertTrue(wait_until_gone(pids['worker']))
        result = gui_host.launch(self.settings(), gui_dir=self.gui, worker_dir=self.fx.worker,
                                 adapters=self.fx.adapters, log=lambda *_: None)
        self.assertEqual(result['exitCode'], 0)

    def test_stale_session_cleanup_preserves_linked_snapshot(self):
        first = gui_host.launch(self.settings(), gui_dir=self.gui, worker_dir=self.fx.worker,
                                adapters=self.fx.adapters, log=lambda *_: None, keep_run_dir=True)
        self.assertEqual(first['exitCode'], 0)
        second = gui_host.launch(self.settings(), gui_dir=self.gui, worker_dir=self.fx.worker,
                                 adapters=self.fx.adapters, log=lambda *_: None)
        self.assertEqual(second['exitCode'], 0)
        vh.load_snapshot(self.fx.snapshot, full=True)


if __name__ == '__main__':
    unittest.main()
