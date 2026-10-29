"""Private execution boundaries, with native cleanup checked only in a valid PID namespace."""
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import private_validation as pv

PROC_VISIBLE = sys.platform == 'linux' and os.readlink('/proc/self') == str(os.getpid())
ENV = {'GITHUB_REPOSITORY':'pengin0503/RimWorld-for-mod-test','GITHUB_REF':'refs/heads/main',
       'GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'100','GITHUB_RUN_ATTEMPT':'1'}


def alive(pid):
    try: return Path(f'/proc/{pid}/stat').read_bytes().rsplit(b')',1)[1].split()[0] != b'Z'
    except OSError: return False


class PreparationTests(unittest.TestCase):
    def test_cow_does_not_prepare_game_and_game_is_prepared_only_once(self):
        from tools import codex_workflow as cw
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,ENV,clear=True):
            root=Path(d); pv.init_session(root,'cow')
            with patch.object(cw,'prepare',side_effect=AssertionError('cow contacted R2')):
                pv.prepare_session(root)
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,ENV,clear=True):
            root=Path(d); session=pv.init_session(root,'all'); calls=[]
            def prepare(args): calls.append(args.private_root); (root/'game-snapshot').mkdir(); return {'status':'prepared'}
            with patch.object(cw,'prepare',side_effect=prepare):
                pv.prepare_session(root); pv.prepare_session(root)
            self.assertEqual(len(calls),1)
            self.assertTrue(pv.read_json(session/'session.json')['gameReady'])

    def test_failed_game_preparation_keeps_cow_runnable(self):
        from tools import codex_workflow as cw
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,ENV,clear=True):
            root=Path(d); pv.init_session(root,'all')
            with patch.object(cw,'prepare',side_effect=RuntimeError('PRIVATE')):
                with self.assertRaises(RuntimeError): pv.prepare_session(root)
            session,manifest=pv.load_session(root)
            self.assertFalse(manifest['gameReady'])
            self.assertFalse(pv.publish_session(root)['acceptancePassed'])

    def test_mismatched_procfs_refuses_to_launch(self):
        with tempfile.TemporaryDirectory() as d, patch.object(os,'readlink',return_value='999999999'):
            root=Path(d); marker=root/'launched'
            result=pv.run_command([sys.executable,'-c',f'open({str(marker)!r},"w").close()'],root/'log')
            self.assertTrue(result['interrupted']); self.assertFalse(marker.exists())


@unittest.skipUnless(PROC_VISIBLE,'native Linux PID/proc namespace required')
class NativeExecutionTests(unittest.TestCase):
    def test_worker_does_not_inherit_cloud_or_github_credentials(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{'AWS_ACCESS_KEY_ID':'PRIVATE','GITHUB_TOKEN':'PRIVATE','R2_ENDPOINT':'PRIVATE'}):
            root=Path(d); out=root/'env.json'
            result=pv.run_command([sys.executable,'-c',f'import os,json; open({str(out)!r},"w").write(json.dumps(dict(os.environ)))'],root/'log')
            self.assertEqual(result['exitCode'],0)
            value=out.read_text(); self.assertNotIn('PRIVATE',value)

    def test_timeout_recovers_detached_descendant(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); pidfile=root/'pid'
            code=f'import subprocess,time; p=subprocess.Popen(["/bin/sleep","60"],start_new_session=True); open({str(pidfile)!r},"w").write(str(p.pid)); time.sleep(60)'
            try:
                result=pv.run_command([sys.executable,'-c',code],root/'log',timeout=.4)
                self.assertTrue(result['interrupted']); self.assertTrue(pidfile.exists())
                self.assertFalse(alive(int(pidfile.read_text())))
            finally:
                if pidfile.exists() and alive(int(pidfile.read_text())): os.kill(int(pidfile.read_text()),signal.SIGKILL)

    def test_orchestrator_cancellation_recovers_detached_descendant(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); pidfile=root/'pid'; runner=root/'runner.py'
            child=f'import subprocess,time; p=subprocess.Popen(["/bin/sleep","60"],start_new_session=True); open({str(pidfile)!r},"w").write(str(p.pid)); time.sleep(60)'
            runner.write_text(f'import sys; sys.path.insert(0,{str(pv.REPO)!r}); from tools import private_validation as p; from pathlib import Path; p.install_stop_handlers(); p.run_command([sys.executable,"-c",{child!r}],Path({str(root/"log")!r}))')
            process=subprocess.Popen([sys.executable,str(runner)])
            try:
                deadline=time.monotonic()+5
                while not pidfile.exists() and time.monotonic()<deadline: time.sleep(.02)
                self.assertTrue(pidfile.exists()); process.terminate(); process.wait(timeout=5)
                self.assertFalse(alive(int(pidfile.read_text())))
            finally:
                if process.poll() is None: process.kill(); process.wait()
                if pidfile.exists() and alive(int(pidfile.read_text())): os.kill(int(pidfile.read_text()),signal.SIGKILL)

    def test_prerequisite_failures_do_not_suppress_independent_suites(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); calls=[]
            def commands(name,*_):
                return [([sys.executable,'-c',f'open({str(root/name)!r},"w").close()'],root/(name+'-evidence'))]
            with patch.object(pv,'suite_commands',side_effect=commands):
                data=pv.run_suites(('smoke','cow'),root/'snapshot',root/'out',root/'worker',
                                   prerequisites={'game':True,'harmony':True,'cow':False})
                self.assertTrue((root/'smoke').exists()); self.assertFalse((root/'cow').exists())
                self.assertTrue(data['suites'][1]['blocked'])
            with patch.object(pv,'suite_commands',side_effect=commands):
                data=pv.run_suites(('smoke','cow'),root/'snapshot',root/'out2',root/'worker',
                                   prerequisites={'game':False,'harmony':False,'cow':True})
                self.assertTrue(data['suites'][0]['blocked']); self.assertTrue((root/'cow').exists())

    def test_failed_suite_keeps_running_and_checkpoint_survives(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            def commands(name,*_):
                return [([sys.executable,'-c','raise SystemExit(1)' if name=='smoke' else 'pass'],root/name)]
            with patch.object(pv,'suite_commands',side_effect=commands):
                data=pv.run_suites(('smoke','cow'),None,root/'out',root/'worker')
            self.assertEqual([x['processes'][0]['exitCode'] for x in data['suites']],[1,0])
            self.assertEqual(len(pv.read_json(root/'out/summary.json')['suites']),2)


@unittest.skipUnless(PROC_VISIBLE and shutil.which('dotnet'), 'native Linux and installed .NET SDK required')
class DotnetExecutionTests(unittest.TestCase):
    def test_fixture_build_finishes_without_background_compiler_descendants(self):
        # Force this job's test build to own a fresh compiler server if it uses one.
        subprocess.run(['dotnet','build-server','shutdown'],capture_output=True,timeout=30,check=True)
        sdks=subprocess.check_output(['dotnet','--list-sdks'],text=True)
        major=max(int(line.split('.')[0]) for line in sdks.splitlines() if line[:1].isdigit())
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); project=root/'fixture.csproj'
            project.write_text(f'<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net{major}.0</TargetFramework><OutputType>Library</OutputType></PropertyGroup></Project>')
            (root/'Fixture.cs').write_text('public static class Fixture { public static int Value => 42; }')
            result=pv.run_command(['dotnet','build',str(project),'--nologo'],root/'build.log',timeout=90)
            self.assertEqual(result['exitCode'],0, (root/'build.log').read_text()[-2000:])
            self.assertFalse(result['interrupted'],'fixture build left a background compiler process')
