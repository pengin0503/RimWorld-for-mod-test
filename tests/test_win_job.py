"""Tests of the Windows Job Object supervision (tools/win_job.py). Windows only; no game file."""
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

WINDOWS = sys.platform == 'win32'
if WINDOWS:
    from tools import win_job

MiB = 1024 * 1024


@unittest.skipUnless(WINDOWS, 'Job Objects exist on Windows only')
class JobTests(unittest.TestCase):
    def run_in_job(self, code, limit):
        job = win_job.Job(limit)
        self.addCleanup(job.close)
        with tempfile.TemporaryDirectory() as temp:
            out, err = Path(temp) / 'out', Path(temp) / 'err'
            with open(out, 'wb') as stdout, open(err, 'wb') as stderr:
                process = job.start([sys.executable, '-c', code], cwd=temp, env=None, stdout=stdout, stderr=stderr)
            try:
                code = process.wait(60)
            finally:
                if process.poll() is None:
                    job.terminate()
            time.sleep(0.2)
            info = job._query(win_job._ExtendedLimit(), win_job.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION)
            report = {'exitCode': code, 'messages': sorted(job.poll_messages()), 'peak': job.peak_memory(),
                      'limitFlags': hex(info.BasicLimitInformation.LimitFlags), 'jobMemoryLimit': info.JobMemoryLimit,
                      'stdout': out.read_text(errors='replace')[-500:], 'stderr': err.read_text(errors='replace')[-500:]}
        return report

    def test_commit_over_the_limit_fails(self):
        report = self.run_in_job('b = bytearray(400 * 1024 * 1024); print("allocated")', 256 * MiB)
        self.assertNotIn('allocated', report['stdout'], report)
        self.assertIn('MemoryError', report['stderr'], report)
        self.assertIn('memoryLimit', report['messages'], report)
        self.assertLessEqual(report['peak'], 256 * MiB, report)

    def test_child_processes_join_the_job_and_die_with_it(self):
        job = win_job.Job(1024 * MiB)
        self.addCleanup(job.close)
        process = job.start([sys.executable, '-c', 'import subprocess, sys, time; '
                             'subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"]); time.sleep(600)'],
                            cwd=None, env=None, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 30
        while job.active_processes() < 2 and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertEqual(job.active_processes(), 2)
        job.terminate()
        process.wait(30)
        deadline = time.monotonic() + 10
        while job.active_processes() and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertEqual(job.active_processes(), 0)


if __name__ == '__main__':
    unittest.main()
