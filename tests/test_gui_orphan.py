"""Linux GUI shutdown must stop a Worker in its own session."""
import json
import os
from pathlib import Path
import signal
import sys
import subprocess
import tempfile
import time
import unittest
from tools import gui_host
from tests.test_validation_host import pid_alive, wait_until_gone

@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux process groups')
class DetachedWorkerTests(unittest.TestCase):
    def test_detached_worker_is_stopped_on_gui_exit(self):
        with tempfile.TemporaryDirectory() as t:
            run = Path(t)
            (run / 'host').mkdir()
            (run / 'gui-request.json').write_text('{}')
            worker_file = run / 'worker.pid'
            controller_file = run / 'controller.pid'
            controller = '''import os, subprocess, sys, time
p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],start_new_session=True)
open(sys.argv[1],'w').write(str(p.pid))
open(sys.argv[2],'w').write(str(os.getpid()))
time.sleep(60)
'''
            gui = f'''#!/usr/bin/env python3
import subprocess,sys,time
from pathlib import Path
subprocess.Popen([sys.executable,'-c',{controller!r},{str(worker_file)!r},{str(controller_file)!r}])
for _ in range(100):
 if Path({str(worker_file)!r}).exists():break
 time.sleep(.02)
'''
            exe = run / 'host' / gui_host.GUI_NAME
            exe.write_text(gui)
            exe.chmod(0o700)
            worker = None
            try:
                result = gui_host.run_gui(run, 512, gui_host.gui_environment(run, 512), poll=.05)
                worker = int(worker_file.read_text())
                controller_pid = int(controller_file.read_text())
                self.assertEqual(result['exitCode'], 0)
                self.assertTrue(wait_until_gone(controller_pid))
                self.assertTrue(wait_until_gone(worker), 'detached worker survived GUI exit')
            finally:
                if worker and pid_alive(worker):
                    os.kill(worker, signal.SIGKILL)
                    wait_until_gone(worker)

    def test_interrupt_preserves_keyboard_interrupt_and_stops_gui(self):
        with tempfile.TemporaryDirectory() as t:
            run = Path(t)
            (run / 'host').mkdir()
            (run / 'gui-request.json').write_text('{}')
            ready = run / 'ready'
            exe = run / 'host' / gui_host.GUI_NAME
            exe.write_text(f"#!/usr/bin/env python3\nimport time\nfrom pathlib import Path\nPath({str(ready)!r}).touch()\ntime.sleep(60)\n")
            exe.chmod(0o700)
            script = "from pathlib import Path; import sys; from tools import gui_host; p=Path(sys.argv[1]); gui_host.run_gui(p, 512, gui_host.gui_environment(p, 512), poll=.05)"
            proc = subprocess.Popen([sys.executable, '-c', script, str(run)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 10
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(ready.exists())
                proc.send_signal(signal.SIGINT)
                _, err = proc.communicate(timeout=10)
                self.assertIn(b'KeyboardInterrupt', err)
                self.assertNotIn(b'UnboundLocalError', err)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.communicate()

    def test_memory_stop_does_not_report_success_exit_code(self):
        with tempfile.TemporaryDirectory() as t:
            run = Path(t)
            (run / 'host').mkdir()
            (run / 'gui-request.json').write_text('{}')
            exe = run / 'host' / gui_host.GUI_NAME
            exe.write_text("#!/usr/bin/env python3\nimport time\nblock=bytearray(100*1024*1024)\ntime.sleep(60)\n")
            exe.chmod(0o700)
            result = gui_host.run_gui(run, 40, gui_host.gui_environment(run, 40), poll=.1)
            self.assertEqual(result['killedFor'], 'memoryLimit')
            self.assertNotEqual(result['exitCode'], 0)
