"""Fixed Linux private validation entry. Raw helper output is never public output."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
SUITES = ('smoke', 'c-regression', 'd-regression', 'd-compare', 'cow')


def resolve_suites(name):
    if name == 'all':
        return SUITES
    if name not in SUITES:
        raise ValueError('unknown suite')
    return (name,)


def current_identity(env=None):
    env = os.environ if env is None else env
    if (env.get('GITHUB_REPOSITORY') != 'pengin0503/RimWorld-for-mod-test'
            or env.get('GITHUB_REF') != 'refs/heads/main'
            or not re.fullmatch('[a-f0-9]{40}', env.get('GITHUB_SHA', ''))
            or any(not re.fullmatch('[1-9][0-9]{0,19}', env.get(n, ''))
                   for n in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))):
        raise ValueError('private validation requires the main workflow identity')
    return {'runId': env['GITHUB_RUN_ID'] + '-' + env['GITHUB_RUN_ATTEMPT'], 'commit': env['GITHUB_SHA']}


def read_json(path):
    try:
        if path.stat().st_size > 4 * 1024 * 1024:
            return {}
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def public_summary(raw, identity):
    """Rebuild from fixed fields. Identity is trusted workflow context, never evidence."""
    raw = raw if isinstance(raw, dict) else {}
    try:
        selected = resolve_suites(raw.get('selection'))
    except ValueError:
        selected = ()
    bound = all(raw.get(k) == v for k, v in identity.items())
    source = raw.get('suites') if isinstance(raw.get('suites'), list) and bound else []
    order = [r.get('suite') if isinstance(r, dict) else None for r in source]
    rows = []
    for name in selected:
        matches = [r for r in source if isinstance(r, dict) and r.get('suite') == name]
        r = matches[0] if len(matches) == 1 else {}
        processes = r.get('processes') if isinstance(r.get('processes'), list) else []
        safe = []
        for p in processes[:2]:
            p = p if isinstance(p, dict) else {}
            code = p.get('exitCode'); seconds = p.get('seconds')
            safe.append({'exitCode': code if type(code) is int and -255 <= code <= 255 else None,
                         'interrupted': p.get('interrupted') is not False,
                         'seconds': seconds if type(seconds) in (int, float) and math.isfinite(seconds)
                         and 0 <= seconds <= 2700 else None})
        checks = r.get('checks') if isinstance(r.get('checks'), dict) else {}
        expected_processes = 2 if name == 'c-regression' else 1
        started = r.get('started') is True
        blocked = r.get('blocked') is True and not started and not processes
        complete = (started and len(processes) == expected_processes and len(safe) == expected_processes
                    and all(p['exitCode'] is not None and not p['interrupted'] for p in safe)
                    and checks.get('complete') is True)
        accepted = complete and all(p['exitCode'] == 0 for p in safe) and checks.get('accepted') is True
        qualified = accepted and name == 'smoke' and checks.get('qualified') is True
        failed = complete and r.get('demonstratedFailure') is True
        status = 'blocked' if blocked else 'failed' if failed else 'passed' if qualified or (accepted and name == 'cow') else 'incomplete'
        rows.append({'suite': name, 'executionStatus': 'completed' if complete else 'interrupted' if started else 'notStarted',
                     'validationStatus': status, 'qualificationStatus': 'qualified' if qualified else
                     'experimental' if name != 'cow' else 'notRequested', 'acceptancePassed': accepted,
                     'processes': safe})
    accepted = bool(rows) and order == list(selected) and all(r['acceptancePassed'] for r in rows)
    status = ('failed' if any(r['validationStatus'] == 'failed' for r in rows) else
              'blocked' if any(r['validationStatus'] == 'blocked' for r in rows) else
              'passed' if accepted and all(r['validationStatus'] == 'passed' for r in rows) else 'incomplete')
    return {**identity, 'selection': raw.get('selection') if selected else None, 'suites': rows,
            'acceptancePassed': accepted, 'executionStatus': 'completed' if rows and order == list(selected)
            and all(r['executionStatus'] == 'completed' for r in rows) else 'interrupted' if any(
                r['executionStatus'] != 'notStarted' for r in rows) else 'notStarted',
            'validationStatus': status, 'qualificationStatus': 'qualified' if accepted and all(
                r['qualificationStatus'] == 'qualified' for r in rows) else
            'experimental' if any(r['qualificationStatus'] == 'experimental' for r in rows) else 'notRequested'}


def session_path(root):
    from tools import codex_workflow as cw
    return cw._safe_private(root) / 'validation' / current_identity()['runId']


def init_session(root, selection):
    suites = resolve_suites(selection)
    identity = current_identity()
    session = session_path(root)
    if session.exists():
        write_json(session / 'summary.json', {**identity, 'selection': selection, 'suites': []})
        manifest = read_json(session / 'session.json'); manifest['invalidated'] = True
        write_json(session / 'session.json', manifest)
        raise ValueError('session already initialized')
    session.mkdir(parents=True, mode=0o700)
    write_json(session / 'session.json', {**identity, 'selection': selection,
        'needsGame': any(s != 'cow' for s in suites), 'needsHarmony': any(s in ('smoke','d-compare') for s in suites),
        'needsCow': 'cow' in suites})
    write_json(session / 'summary.json', {**identity, 'selection': selection, 'suites': []})
    return session


def load_session(root):
    session = session_path(root); manifest = read_json(session / 'session.json')
    if (not isinstance(manifest, dict) or manifest.get('invalidated') or
            any(manifest.get(k) != v for k, v in current_identity().items())):
        raise ValueError('invalid session')
    resolve_suites(manifest.get('selection'))
    return session, manifest


def publish_session(root):
    try:
        session, manifest = load_session(root)
        checkpoint = session / 'execution/summary.json'
        raw = read_json(checkpoint if manifest.get('executionAttempted') and checkpoint.is_file() else session / 'summary.json')
        if not isinstance(raw, dict) or raw.get('selection') != manifest['selection']:
            raw = {}
    except ValueError:
        raw = {}
    return public_summary(raw, current_identity())


def native_process_available():
    try:
        if sys.platform != 'linux' or os.readlink('/proc/self') != str(os.getpid()):
            return False
        probe = os.pidfd_open(os.getpid())
        try: signal.pidfd_send_signal(probe, 0)
        finally: os.close(probe)
        return True
    except (OSError, AttributeError):
        return False


def child_environment(private):
    allowed = ('PATH','DOTNET_ROOT','LD_LIBRARY_PATH','SSL_CERT_FILE','SSL_CERT_DIR','RUNNER_TRACKING_ID')
    env = {k: os.environ[k] for k in allowed if k in os.environ}
    for name in ('home','tmp','config','cache'):
        (private/name).mkdir(parents=True,exist_ok=True,mode=0o700)
    env.update(HOME=str(private/'home'), TMPDIR=str(private/'tmp'), XDG_CONFIG_HOME=str(private/'config'),
               XDG_CACHE_HOME=str(private/'cache'), DOTNET_CLI_TELEMETRY_OPTOUT='1',
               DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1', UseSharedCompilation='false', MSBUILDDISABLENODEREUSE='1', DOTNET_CLI_USE_MSBUILD_SERVER='0')
    return env


def tree_rss(pid):
    from tools.gui_linux_supervisor import children_of
    total = 0
    for child in [pid, *children_of(pid)]:
        try: total += int(Path(f'/proc/{child}/statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')
        except (OSError,ValueError,IndexError): pass
    return total


def run_command(command, log, *, timeout=900, memory_limit=4*1024**3):
    started=time.monotonic(); interrupted=False
    if not native_process_available():
        return {'exitCode':None,'interrupted':True,'seconds':0}
    log=log.resolve()
    log.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    status=log.with_suffix('.guardian.json')
    if status.exists() or Path(str(status)+'.inner').exists():
        raise ValueError('guardian status already exists')
    # The existing Linux subreaper pins descendants by pidfd, including helpers
    # that call setsid. Killing only this wrapper's process group leaks Workers.
    wrapped=[sys.executable,str(REPO/'tools/gui_linux_supervisor.py'),str(status),'-1',*command]
    with log.open('xb') as stream:
        process=subprocess.Popen(wrapped,stdout=stream,stderr=subprocess.STDOUT,
                                 env=child_environment(log.parent/'environment'),start_new_session=True,cwd=REPO)
        try:
            while process.poll() is None:
                if (time.monotonic()-started>=timeout or log.stat().st_size>8*1024*1024
                        or tree_rss(process.pid)>memory_limit):
                    interrupted=True; break
                time.sleep(.05)
        finally:
            # Give the subreaper ownership of cleanup; do not kill it before it
            # has recovered nested sessions. Kernel I/O may delay actual exit.
            if process.poll() is None:
                process.terminate()
            process.wait()
    if log.stat().st_size > 8*1024*1024 or time.monotonic()-started >= timeout:
        interrupted=True
    evidence=read_json(status)
    evidence=evidence if isinstance(evidence,dict) else {}
    code=evidence.get('exitCode')
    valid=(process.returncode==0 and type(code) is int and -255<=code<=255
           and type(evidence.get('strayProcessesKilled')) is bool)
    interrupted |= not valid or evidence.get('strayProcessesKilled') is True
    return {'exitCode':code if valid else None,'interrupted':interrupted,'seconds':round(time.monotonic()-started,3)}


def install_stop_handlers():
    def stop(_signum,_frame): raise SystemExit(130)
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP): signal.signal(sig,stop)


def prepare_session(root):
    from tools import codex_workflow as cw
    session, manifest=load_session(root)
    if not manifest['needsGame']: return
    if manifest.get('preparationAttempted'):
        if manifest.get('gameReady') is not True: raise ValueError('previous preparation failed')
        return
    manifest.update(preparationAttempted=True,gameReady=False)
    write_json(session/'session.json',manifest)
    try:
        accounting = cw.prepare(SimpleNamespace(private_root=root,refresh=False,aws='aws'))
        write_json(session/'preparation.json', accounting)
        manifest['gameReady']=True
    finally: write_json(session/'session.json',manifest)


def suite_commands(name, snapshot, out, worker, harmony=None, cow=None):
    def helper(path,dest,*args):
        return ([sys.executable,str(REPO/path),'--snapshot',str(snapshot),'--out',str(dest),'--worker',str(worker),*args],dest)
    if name=='smoke':
        return [helper('tests/integration/run_fixture_matrix.py',out/'smoke',
                       '--harmony-dll',str(harmony),'--cases','ok,harmony-ok,map-ok')]
    if name=='c-regression':
        return [helper('tests/integration/run_bill_ingredients.py',out/'materials'),
                helper('tests/integration/run_event_choice.py',out/'events')]
    if name=='d-regression': return [helper('tests/integration/run_bounded_tick.py',out/'ticks')]
    if name=='d-compare': return [helper('experiments/official-comparison/compare_ticks.py',out/'comparison','--harmony-dll',str(harmony))]
    if name=='cow':
        return [([sys.executable,str(REPO/'experiments/cow-measurement/measure.py'),
                  '--root',str(cow/'measurement'),'--summary',str(out/'summary.json')],out)]
    raise ValueError('unknown suite')


def run_suites(suites, snapshot, out, worker, *, harmony=None, cow=None, prerequisites=None, identity=None, selection=None):
    from tools.private_validation_evidence import inspect
    if any(n not in SUITES for n in suites) or len(set(suites))!=len(suites): raise ValueError('invalid suites')
    out.mkdir(parents=True,exist_ok=True,mode=0o700)
    identity = identity or {}; prerequisites = prerequisites if prerequisites is not None else {'game':True,'harmony':True,'cow':True}
    data={**identity,'selection':selection,'suites':[{'suite':n,'started':False,'blocked':False,'processes':[],'checks':{}} for n in suites]}
    def checkpoint(): write_json(out/'summary.json',data)
    checkpoint(); deadline=time.monotonic()+2400
    for row in data['suites']:
        name=row['suite']; required=('cow',) if name=='cow' else ('game','harmony') if name in ('smoke','d-compare') else ('game',)
        if not all(prerequisites.get(k) is True for k in required):
            row['blocked']=True; checkpoint(); continue
        if time.monotonic()>=deadline: continue
        row['started']=True; checkpoint()
        destination=out/name; destination.mkdir(mode=0o700)
        results=[]
        try:
            commands=suite_commands(name,snapshot,destination,worker,harmony,cow)
            for i,(command,evidence) in enumerate(commands):
                if time.monotonic()>=deadline: break
                row['processes'].append({'exitCode':None,'interrupted':True,'seconds':0}); checkpoint()
                row['processes'][-1]=run_command(command,destination/f'helper-{i}.log',timeout=min(900,deadline-time.monotonic()))
                kind=('materials','events')[i] if name=='c-regression' else name
                results.append(inspect(kind,evidence)); checkpoint()
            row['checks']={'complete':len(results)==len(commands) and all(r['complete'] for r in results),
                           'accepted':len(results)==len(commands) and all(r['accepted'] for r in results),
                           'qualified':name=='smoke' and bool(results) and results[0]['qualified']}
            row['demonstratedFailure']=any(r['failed'] for r in results)
        except (OSError,ValueError,RuntimeError):
            row['checks']={}
        finally: checkpoint()
    return data


def cow_ready(root):
    if root is None or not root.is_dir(): return False
    try:
        result=subprocess.run(['findmnt','-n','-o','FSTYPE','-T',str(root)],capture_output=True,text=True,timeout=5,check=False)
        return result.returncode==0 and result.stdout.strip()=='btrfs'
    except (OSError,subprocess.TimeoutExpired): return False


def execute_session(root, worker, harmony=None, cow=None):
    session, manifest=load_session(root)
    if manifest.get('executionAttempted'):
        manifest['invalidated']=True; write_json(session/'session.json',manifest)
        raise ValueError('session already executed')
    manifest['executionAttempted']=True; write_json(session/'session.json',manifest)
    run_suites(resolve_suites(manifest['selection']),root/'game-snapshot',session/'execution',worker,
               harmony=harmony,cow=cow,identity=current_identity(),selection=manifest['selection'],
               prerequisites={'game':manifest.get('gameReady') is True and (root/'game-snapshot').is_dir()
                              and (worker/'RimWorldValidationWorker.dll').is_file(),
                              'harmony':harmony is not None and harmony.is_file(),'cow':cow_ready(cow)})
    write_json(session/'summary.json',read_json(session/'execution/summary.json'))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('init','prepare','run','publish'))
    parser.add_argument('--suite',default='smoke',choices=(*SUITES,'all'))
    parser.add_argument('--private-root',type=Path,required=True)
    parser.add_argument('--worker',type=Path,default=REPO/'worker/bin')
    parser.add_argument('--harmony-dll',type=Path)
    parser.add_argument('--cow-root',type=Path)
    args=parser.parse_args(argv)
    try:
        current_identity(); resolve_suites(args.suite)
        if args.phase=='init':
            if not native_process_available(): raise ValueError('unsupported native process environment')
            session=init_session(args.private_root,args.suite); manifest=read_json(session/'session.json')
            with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as stream:
                for k in ('needsGame','needsHarmony','needsCow'): stream.write(f'{k}={str(manifest[k]).lower()}\n')
        elif args.phase=='prepare': prepare_session(args.private_root)
        elif args.phase=='run':
            install_stop_handlers()
            try: execute_session(args.private_root,args.worker.resolve(),args.harmony_dll,args.cow_root)
            finally:
                session,_=load_session(args.private_root)
                if (session/'execution/summary.json').is_file():
                    write_json(session/'summary.json',read_json(session/'execution/summary.json'))
            return 0 if publish_session(args.private_root)['acceptancePassed'] else 1
        else:
            public=publish_session(args.private_root)
            print(json.dumps(public,indent=2,allow_nan=False))
            return 0 if public['acceptancePassed'] else 1
        return 0
    except (OSError,ValueError,RuntimeError,KeyError):
        print('Private validation unavailable; inspect private evidence',file=sys.stderr)
        return 1


if __name__=='__main__': raise SystemExit(main())
