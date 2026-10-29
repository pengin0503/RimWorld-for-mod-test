"""Private finite-tick acceptance; stdout contains only whitelisted results."""
import argparse
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from tools import validation_host as vh


def child_stopped(path):
    if not path.is_file():
        return False
    try:
        pid = int(path.read_text())
        if pid <= 1:
            return False
        deadline = time.monotonic() + 5
        while True:
            try:
                state = Path(f'/proc/{pid}/stat').read_text().split(')')[1].split()[0]
                if state == 'Z':
                    return True
            except (FileNotFoundError, ProcessLookupError):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)
    except (OSError, ValueError, IndexError):
        return False


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--worker', default=str(REPO / 'worker/bin'))
    a = p.parse_args()
    out = Path(a.out).resolve()
    if out.exists() or out == REPO or REPO in out.parents:
        p.error('--out must be a new directory outside checkout')
    out.mkdir(mode=0o700, parents=True)
    snapshot = Path(a.snapshot).resolve()
    probe = out / 'probe'
    shutil.copytree(REPO / 'tests/fixtures/validation-mods/tickprobe', probe)
    with (out / 'build.log').open('w') as log:
        subprocess.run(['dotnet', 'build', str(REPO / 'tests/fixtures/validation-mods-src/TickProbe'),
                        '-c', 'Release', '-o', str(probe / 'Assemblies'),
                        f'-p:GameManagedDir={snapshot / "game"}', '--nologo'],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    target = out / 'target'
    shutil.copytree(REPO / 'tests/fixtures/validation-mods/okxml', target)
    rows = []
    summary = out / 'safe-summary.json'
    def run(name, *, count=600, expected=None, observer='fixture.counter', mode=None, missing=False, limits=None):
        if mode:
            defs = target / 'Defs'; defs.mkdir(exist_ok=True)
            (defs / 'Tick.xml').write_text('<Defs><RWMT.TickProbe.TickProbeConfigDef>'
                '<defName>RWMT_TickConfig</defName><mode>' + mode + '</mode>'
                '</RWMT.TickProbe.TickProbeConfigDef></Defs>')
        else:
            (target / 'Defs/Tick.xml').unlink(missing_ok=True)
        mods = [{'path': str(probe)}, {'path': str(target), 'target': True}]
        if missing: mods = mods[1:]
        request = {'recordType': 'modValidationRequest', 'schemaVersion': 1, 'levels': ['A', 'D'],
            'mods': mods, 'map': {'seed': 'RWMT-tick'}, 'tests': ['bounded-tick.v1'],
            'tick': {'count': count, 'observeAt': [0, 60] if count == 60 else [0, 60, count]},
            'expectations': {'tickObservations': [{'tick': count, 'id': observer,
                                                 'equals': count if expected is None else expected}]},
            'limits': limits or {'timeoutSeconds': 180}}
        path = out / (name + '.json'); path.write_text(json.dumps(request))
        r = vh.run_validation(snapshot, path, out / name, a.worker, baseline_cache=out / 'baseline-cache')
        stage = r.get('stages', {}).get('D', {})
        codes = [x['code'] for x in r.get('reasons', [])]
        want = 'failed' if expected is not None else 'incomplete' if observer != 'fixture.counter' or missing or mode else 'completed'
        ok = r['status'] == 'incomplete' and stage.get('status') == want and 'dNotQualified' in codes
        cleanup = None
        if mode in ('hang', 'memory', 'log'):
            cleanup = child_stopped(out / name / 'target/home/tick-probe-child.pid')
            ok &= cleanup
        if mode:
            ok &= 'tickObservationIncomplete' in codes
            ok &= [o.get('tick') for o in (stage.get('evidence') or {}).get('observations', [])] == [0, 60]
            if mode == 'memory':
                ok &= 'memoryLimit' in codes
            if mode == 'log':
                ok &= 'logLimit' in codes
            if mode == 'hang':
                ok &= r['executionStatus'] == 'interrupted'
        if not mode and not missing and observer == 'fixture.counter':
            ok &= r['executionStatus'] == 'completed' and not set(codes).intersection(
                {'newErrors', 'newWarnings', 'baselineIncomplete', 'tickObservationIncomplete'})
        tick = stage.get('evidence') or {}
        tick_error = tick.get('error') or ''
        fault_text = tick_error + '\n' + '\n'.join(str(e.get('message', '')) for e in r.get('diagnostics', {}).get('newInTarget', []))
        for run_name in ('baseline', 'target'):
            event_path = out / name / run_name / 'events.jsonl'
            if event_path.is_file():
                for line in event_path.read_text(errors='replace').splitlines()[:2000]:
                    try:
                        event = json.loads(line)
                        if event.get('level') == 'error': fault_text += '\n' + str(event.get('message', ''))
                    except ValueError:
                        pass
        fault_types = sorted(set(re.findall(r'\b(?:[A-Za-z_][A-Za-z0-9_]*\.)*[A-Za-z_][A-Za-z0-9_]*Exception\b', fault_text)))[:8]
        fault_methods = sorted(set(re.findall(r'\bat ([A-Za-z_][A-Za-z0-9_.+`]*)(?=\()', fault_text)))[:12]
        member = re.search(r'adapter member not found: ([A-Za-z0-9_.(),]+)', tick_error)
        rows.append({'faultTypes': fault_types, 'faultMethods': fault_methods, 'errorType': (re.match(r'^[A-Za-z][A-Za-z0-9_.+`]*Exception', tick_error).group(0)
                                   if re.match(r'^[A-Za-z][A-Za-z0-9_.+`]*Exception', tick_error) else None),
                     'missingMember': member.group(1) if member else None, 'case': name, 'ok': bool(ok), 'status': r['status'], 'D': stage.get('status'),
                     'executionStatus': r['executionStatus'], 'codes': codes,
                     'advanced': tick.get('advanced'), 'startTick': tick.get('startTick'), 'endTick': tick.get('endTick'),
                     'observations': [{'tick': o.get('tick'), 'gameTick': o.get('gameTick'),
                                       'counter': o.get('values', {}).get('fixture.counter')}
                                      for o in tick.get('observations', [])],
                     'baselineCached': r.get('diagnostics', {}).get('baselineCached'), 'descendantsStopped': cleanup,
                     'stop': (r.get('process', {}).get('target') or {}).get('killedFor')})
        summary.write_text(json.dumps({'runs': rows, 'ok': all(x['ok'] for x in rows)}, indent=2))
        # Whitelist errors' type names and stages, never messages/paths/stack traces.
        if not ok:
            worker_path = out / name / 'target/worker-result.json'
            if worker_path.is_file():
                wr = json.loads(worker_path.read_text())
                print(json.dumps({'case': name, 'workerStatus': wr.get('executionStatus'),
                    'stages': [{'name': x.get('name'), 'status': x.get('status')} for x in wr.get('stages', [])],
                    'tickErrorType': (wr.get('tick', {}).get('error') or '').split(':', 1)[0].split('\n', 1)[0]}))
        return ok
    # Stop the acceptance run early when the basic call path is not established.
    if not run('ticks-60', count=60): return 1
    run('ticks-600')
    run('ticks-600-reuse')
    run('wrong-value', expected=599)
    run('unknown-id', observer='unknown.counter')
    run('missing-probe', missing=True)
    run('throwing-probe', mode='throw')
    run('timeout', mode='hang', limits={'timeoutSeconds': 30})
    run('memory-limit', mode='memory', limits={'memoryMiB': 1024, 'timeoutSeconds': 180})
    run('log-limit', mode='log', limits={'logMiB': 1, 'timeoutSeconds': 180})
    return 0 if all(r['ok'] for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
