"""Development-only D cross-check using the official quicktest's normal tick loop.

No product module imports this script. Private logs stay outside the checkout.
"""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from tools import validation_host as vh
MARKER = '[RWMT-TICK] '
# Exact known 1.7 diagnostic, compared without publishing the private message.
STEAM_DIAGNOSTIC_SHA256 = 'ee86ee64a1f2a1aad52ddca667ce8b7063ddaa952ce7a9c13ab5969a9d122eca'
OFFICIAL_LOG = re.compile(r'^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+\s+(ERROR|WARN|INFO)\s+\[([^\]]+)\] (.*)$')


def valid_context(view, setup):
    if not isinstance(view, dict) or set(view) != {'width', 'height', 'rootSize', 'x', 'z', 'zoom'}:
        return False
    if any(type(view[k]) is not int or view[k] <= 0 for k in ('width', 'height')):
        return False
    if any(type(view[k]) not in (int, float) or not math.isfinite(view[k]) for k in ('rootSize', 'x', 'z')):
        return False
    if view['rootSize'] != 24 or not all(0 <= view[k] <= 250 for k in ('x', 'z')) or not isinstance(view['zoom'], str) or not view['zoom']:
        return False
    if not isinstance(setup, dict) or set(setup) != {'seed', 'tile', 'biome', 'sizeX', 'sizeZ', 'generator', 'mods'}:
        return False
    return (setup['seed'] == 'rwmt' and setup['sizeX'] == setup['sizeZ'] == 250
        and type(setup['tile']) is int and setup['tile'] >= 0 and setup['biome'] == 'AridShrubland'
        and setup['generator'] == 'Base_Player' and isinstance(setup['mods'], list) and len(setup['mods']) >= 2
        and all(isinstance(n, str) and re.fullmatch(r'[A-Za-z0-9_.-]+', n) for n in setup['mods']))


def compare(product, official, count):
    points = [0, 60] if count == 60 else [0, 60, 600]
    faults = [] if type(count) is int and count in (60, 600) else ['unsupportedCount']
    normalized = []
    for label, evidence in [('product', product), ('official', official)]:
        rows = evidence.get('rows', [])
        if evidence.get('exitCode') != 0 or evidence.get('interrupted') or evidence.get('errors'):
            faults.append(label + '.diagnosticsOrExit')
        started = [r for r in rows if r.get('kind') == 'started']
        observed = [r for r in rows if r.get('kind') == 'point']
        ended = [r for r in rows if r.get('kind') == 'end']
        if len(started) != 1 or len(ended) != 1 or len(rows) != len(points) + 2:
            faults.append(label + '.rowSet')
        if [r.get('kind') for r in rows] != ['started'] + ['point'] * len(points) + ['end']:
            faults.append(label + '.rowOrder')
        start = started[0].get('gameTick') if len(started) == 1 else None
        if type(start) is not int or (started and started[0].get('counter') != 0):
            faults.append(label + '.start')
        if [r.get('relative') for r in observed] != points:
            faults.append(label + '.points')
        for row in observed:
            n = row.get('relative')
            if (type(n) is not int or type(start) is not int or row.get('gameTick') != start + n
                    or row.get('counter') != n or row.get('startedCalls') != 1 or row.get('longEvent') is not False):
                faults.append(label + '.tickInvariant')
            if not valid_context(row.get('view'), row.get('setup')):
                faults.append(label + '.contextMissing')
        if len(ended) == 1 and (ended[0].get('advanced') != count or ended[0].get('counter') != count
                or type(start) is not int or ended[0].get('gameTick') != start + count):
            faults.append(label + '.end')
        normalized.append(observed)
    if normalized[0] != normalized[1]:
        faults.append('independentObservationsDiffer')
    # Expose fixed reason labels only; raw context and diagnostics remain private.
    return {'equivalent': not faults, 'count': count, 'faults': sorted(set(faults)),
            'productPoints': len(normalized[0]), 'officialPoints': len(normalized[1])}


def parse_lines(lines, *, worker=False):
    rows, errors = [], []
    for line in lines:
        if worker:
            event = json.loads(line)
            text = str(event.get('message', ''))
            if event.get('level') in ('error', 'warning') and not vh.known_noise(event):
                errors.append(text)
        else:
            text = line
            match = OFFICIAL_LOG.match(line)
            if match and match[1] in ('ERROR', 'WARN'):
                level, category, message = match.groups()
                steam = (level == 'ERROR' and category == 'Verse'
                    and hashlib.sha256(message.encode()).hexdigest() == STEAM_DIAGNOSTIC_SHA256)
                shutdown = (level == 'WARN' and category == 'NativeAllocationRuntime'
                    and any(r.get('kind') == 'end' for r in rows)
                    and any(n['id'] == 'shutdownNativeAllocations' and n['match'].fullmatch(message) for n in vh.KNOWN_NOISE))
                if not steam and not shutdown: errors.append(line)
            elif re.search(r'\b(?:ERROR|WARN)\s+\[', line):
                errors.append(line)  # malformed diagnostics cannot silently disappear
        if MARKER in text:
            try: rows.append(json.loads(text.split(MARKER, 1)[1]))
            except ValueError: errors.append('invalid observation JSON')
    return {'rows': rows, 'errors': errors}


def build(project, dest, snapshot, harmony):
    subprocess.run(['dotnet', 'build', str(REPO / 'tests/fixtures/validation-mods-src' / project),
        '-c', 'Release', '-o', str(dest), f'-p:GameManagedDir={snapshot / "game"}',
        f'-p:HarmonyDll={harmony}', '--nologo'], check=True, stdout=subprocess.DEVNULL)


def bounded_official(root, timeout=120):
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(root / 'home'),
           'XDG_CONFIG_HOME': str(root / 'xdg'), 'LANG': 'C.UTF-8'}
    start = time.monotonic(); stopped = False
    with (root / 'stdout.log').open('wb') as log:
        proc = subprocess.Popen(['./RimWorld', '-headless', '-quicktest', '-NoCrashDialog'],
            cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            while proc.poll() is None:
                if (time.monotonic() - start > timeout or vh._process_group_rss(proc.pid) > 2 * 1024**3
                        or vh._dir_bytes([root / 'xdg', root / 'stdout.log']) > 8 * 1024**2):
                    stopped = True; break
                time.sleep(0.1)
        finally:
            # Always reap descendants, even if the parent exited by itself.
            try: os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            proc.wait()
    return proc.returncode, stopped, round(time.monotonic() - start, 3)



def summarize_run(product, official, count, *, seconds, product_d):
    row = compare(product, official, count)
    row['differentFields'] = [k for k in ('gameTick', 'counter', 'startedCalls', 'longEvent', 'view', 'setup')
        if [r.get(k) for r in product['rows'] if r.get('kind') == 'point'] !=
           [r.get(k) for r in official['rows'] if r.get('kind') == 'point']]
    row['viewDifferences'] = [k for k in ('width', 'height', 'rootSize', 'x', 'z', 'zoom')
        if [r.get('view', {}).get(k) for r in product['rows'] if r.get('kind') == 'point'] !=
           [r.get('view', {}).get(k) for r in official['rows'] if r.get('kind') == 'point']]
    row['setupDifferences'] = [k for k in ('seed', 'tile', 'sizeX', 'sizeZ', 'biome', 'generator', 'mods')
        if [r.get('setup', {}).get(k) for r in product['rows'] if r.get('kind') == 'point'] !=
           [r.get('setup', {}).get(k) for r in official['rows'] if r.get('kind') == 'point']]
    row['observations'] = {label: [{k:v for k,v in r.items()
        if k in ('relative','gameTick','counter','startedCalls') and type(v) is int and -(2**63) <= v < 2**63}
        for r in evidence['rows'] if r.get('kind') == 'point']
        for label,evidence in [('product',product),('official',official)]}
    row['numericViews'] = {label: [{k:v for k,v in r.get('view', {}).items()
        if k in ('width','height','rootSize','x','z') and type(v) in (int,float) and math.isfinite(v)}
        for r in evidence['rows'] if r.get('kind') == 'point']
        for label,evidence in [('product',product),('official',official)]}
    keywords = ('depend', 'description', 'packageId', 'supportedVersions', 'url', 'incompatible',
                'XML', 'Texture', 'graphics', 'audio', 'camera', 'patch', 'frame')
    row['diagnosticKinds'] = {label: [[k for k in keywords if k.lower() in error.lower()]
        for error in evidence['errors']][:16] for label,evidence in [('product',product),('official',official)]}
    row.update(officialSeconds=seconds if type(seconds) in (int,float) and math.isfinite(seconds) else None,
        officialExitCode=official.get('exitCode') if type(official.get('exitCode')) is int else None,
        productD=product_d if product_d in ('completed','failed','incomplete','notRequested') else None,
        productErrors=len(product['errors']), officialErrors=len(official['errors']))
    return row

def summary_complete(runs):
    return ([r.get('count') for r in runs] == [60, 600, 600]
            and all(r.get('equivalent') is True and r.get('sensitivity') is True for r in runs))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot', type=Path, required=True)
    p.add_argument('--harmony-dll', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--worker', type=Path, default=REPO / 'worker/bin')
    a = p.parse_args(argv)
    a.out = a.out.resolve(); a.snapshot = a.snapshot.resolve(); a.harmony_dll = a.harmony_dll.resolve()
    if a.out.exists() or a.out == REPO or REPO in a.out.parents:
        p.error('--out must be new and outside checkout')
    a.out.mkdir(mode=0o700, parents=True)
    fixtures = a.out / 'fixtures'; fixtures.mkdir()
    for name, project in [('mapprobe', 'MapProbe'), ('tickprobe', 'TickProbe'), ('tickqualification', 'TickQualification')]:
        dest = fixtures / name
        shutil.copytree(REPO / 'tests/fixtures/validation-mods' / name, dest)
        build(project, dest / 'Assemblies', a.snapshot, a.harmony_dll)
    shutil.copytree(REPO / 'tests/fixtures/validation-mods/harmonylib', fixtures / 'harmonylib')
    (fixtures / 'harmonylib/Assemblies').mkdir()
    shutil.copyfile(a.harmony_dll, fixtures / 'harmonylib/Assemblies/0Harmony.dll')
    shutil.copytree(REPO / 'tests/fixtures/validation-mods/okxml', fixtures / 'okxml')
    summary = {'ok': False, 'runs': []}
    # Independent fresh processes; all use the same prepared game snapshot.
    for count in (60, 600, 600):
        rowdir = a.out / f'run-{len(summary["runs"]) + 1}'; rowdir.mkdir()
        defs = fixtures / 'tickqualification/Defs'; defs.mkdir(exist_ok=True)
        def config(official):
            return '<Defs><RWMT.TickQualification.ConfigDef><defName>RWMT_TickQualification</defName>' + \
                f'<official>{str(official).lower()}</official><count>{count}</count></RWMT.TickQualification.ConfigDef></Defs>'
        (defs / 'Config.xml').write_text(config(False))
        request = {'recordType': 'modValidationRequest', 'schemaVersion': 1, 'levels': ['A', 'D'],
            'mods': [{'path': str(fixtures / n), 'target': n == 'okxml'} for n in
                     ('harmonylib', 'mapprobe', 'tickprobe', 'tickqualification', 'okxml')],
            'map': {'seed': 'rwmt'}, 'tests': ['bounded-tick.v1'],
            'tick': {'count': count, 'observeAt': [0, 60] if count == 60 else [0, 60, 600]},
            'expectations': {'tickObservations': [{'tick': count, 'id': 'fixture.counter', 'equals': count}]},
            'limits': {'timeoutSeconds': 180}}
        path = rowdir / 'request.json'; path.write_text(json.dumps(request))
        result = vh.run_validation(a.snapshot, path, rowdir / 'product', a.worker, keep_run_dirs=True)
        target = rowdir / 'product/target'
        events = target / 'events.jsonl'
        product = parse_lines(events.read_text().splitlines(), worker=True) if events.is_file() else {'rows': [], 'errors': ['missing']}
        process = result.get('process', {}).get('target', {})
        product.update(exitCode=process.get('exitCode'), interrupted=result.get('executionStatus') != 'completed')
        # Stage the official executable with exactly the product's copied mods/config.
        root = rowdir / 'official'; root.mkdir()
        game = a.snapshot / 'game'
        for entry in game.iterdir():
            if entry.name not in ('RimWorld', 'Data'):
                (root / entry.name).symlink_to(entry)
        shutil.copyfile(game / 'RimWorld', root / 'RimWorld'); (root / 'RimWorld').chmod(0o700)
        (root / 'Data').mkdir(); (root / 'Data/Core').symlink_to(game / 'Data/Core')
        shutil.copytree(target / 'host/Mods', root / 'Mods')
        # Find only the self-made qualifier by its unique config filename.
        configs = list((root / 'Mods').glob('*/Defs/Config.xml'))
        if len(configs) != 1: raise ValueError('qualifier configuration missing')
        configs[0].write_text(config(True))
        conf = root / 'xdg/unity3d/Ludeon Studios/RimWorld by Ludeon Studios/Config'; conf.mkdir(parents=True)
        for name in ('ModsConfig.xml', 'Prefs.xml'):
            shutil.copyfile(target / 'userdata/Config' / name, conf / name)
        (root / 'home').mkdir()
        code, stopped, seconds = bounded_official(root)
        log = conf.parent / 'Logs/Player.log'
        official = parse_lines(log.read_text(errors='replace').splitlines()) if log.is_file() else {'rows': [], 'errors': ['missing']}
        official.update(exitCode=code, interrupted=stopped)
        (rowdir / 'private-comparison.json').write_text(json.dumps({'product':product,'official':official}, indent=2))
        d = result.get('stages', {}).get('D', {})
        row = summarize_run(product, official, count, seconds=seconds, product_d=d.get('status'))
        if d.get('status') != 'completed' or not vh.bounded_tick.evidence_complete(request['tick'], d.get('evidence')):
            row['equivalent'] = False
            row['faults'].append('productEvidenceIncomplete')
        # Sensitivity: a plausible counter defect must fail the same comparison.
        changed = copy.deepcopy(official)
        for observation in changed['rows']:
            if observation.get('kind') == 'point' and observation.get('relative') == count:
                observation['counter'] -= 1
        row['sensitivity'] = not compare(product, changed, count)['equivalent']
        summary['runs'].append(row)
        summary['ok'] = summary_complete(summary['runs'])
        (a.out / 'safe-summary.json').write_text(json.dumps(summary, indent=2))
        # Continue finite boundary characterization after a view/diagnostic mismatch,
        # but never repeat a missing or interrupted tick call path.
        needed = 2 if count == 60 else 3
        if (row['productPoints'] != needed or row['officialPoints'] != needed
                or d.get('status') != 'completed' or code != 0 or stopped):
            break
    return 0 if summary['ok'] and len(summary['runs']) == 3 else 1

if __name__ == '__main__': raise SystemExit(main())
