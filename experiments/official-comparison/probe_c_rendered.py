"""Development-only research: the real bill dialog in a *rendering* official process.

Follow-up to the C0 material stop (official headless has no OnGUI pass). One invocation
runs the product's non-rendered bill-ingredient-options.v1 case once, then two official
processes that render to a private virtual display (Xvfb + Mesa lavapipe):

* control: the observer is loaded but opens no dialog (rendering-path diagnostics only);
* observer: the real Dialog_BillConfig is opened through the real WindowStack at the
  Entry state and the ingredient rows that the dialog's own code listed are recorded.

The rows are lined up with the product's answer. This never grants C qualification,
never changes product predicates or caches and is not part of the product flow. No input
event is synthesized; the official processes quit by themselves. Game files, raw logs
and screenshots stay in the private --out directory.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from tools import validation_host as vh
from tools import private_validation as pv

MARKER = '[RWMT-RENDERED] '
LOG = re.compile(r'^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+\s+(ERROR|WARN|INFO)\s+\[([^\]]+)\] (.*)$')
REPAINT, LAYOUT = 7, 8
RECIPES = ('RWMT_BillOptions', 'RWMT_BillHidden')
THINGS = ('RWMT_BillGrain', 'RawCorn', 'RawPotatoes')
# The same rows as the private C regression's positive request (run_bill_ingredients.py).
ROWS = (('RWMT_BillHidden', 'RWMT_BillGrain', False, True),
        ('RWMT_BillOptions', 'RWMT_BillGrain', True, True),
        ('RWMT_BillOptions', 'RawCorn', True, False),
        ('RWMT_BillOptions', 'RawPotatoes', False, False))
LVP_ICD = Path('/usr/share/vulkan/icd.d/lvp_icd.json')
PRODUCT_REASONS = {'experimental', 'cNotQualified'}
MIN_PANE_REPAINTS = 3
# Fixed diagnostic classes for the public summary; raw text stays private. Classes are
# only labels: the gate requires the observer run to equal the no-dialog control run.
DIAGNOSTIC_CLASSES = (
    ('steamInit', re.compile(r'^\[Steamworks\.NET\] SteamAPI\.Init\(\) failed\.')),
    ('glfwWaylandUnavailable', re.compile(r'^GLFW Error \(PlatformUnavailable\): Wayland: Platform not initialized$')),
    ('unityDataBeforeInit', re.compile(r"^Used UnityData before it's initialized\.$")),
    ('gpuProbeIncomplete', re.compile(r'^GpuProbe: incomplete after \d+ ms')),
    ('billDialogWindowException', re.compile(r'^Exception filling window for RimWorld\.Dialog_BillConfig:')),
)
CASE_KEYS = ('recipe', 'setup', 'opened', 'openedOnMainThread', 'openEventType', 'otherDialogsBeforeOpen',
             'repaintsWhileOpen', 'freshGameKept', 'removed', 'contents', 'pane', 'ui', 'listing',
             'paneRepaints', 'rowCount', 'exception', 'exceptionKind')


def classify(messages):
    counts = {name: 0 for name, _ in DIAGNOSTIC_CLASSES}
    counts['other'] = 0
    for message in messages:
        name = next((n for n, rx in DIAGNOSTIC_CLASSES if isinstance(message, str) and rx.match(message)), 'other')
        counts[name] += 1
    return counts


def config(official, recipes=RECIPES):
    if type(official) is not bool or any(not isinstance(n, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,64}', n)
                                         for n in (*recipes, *THINGS)):
        raise ValueError('invalid observer configuration')
    items = lambda tag, names: f'<{tag}>' + ''.join(f'<li>{n}</li>' for n in names) + f'</{tag}>'
    return ('<Defs><RWMT.CRendered.ConfigDef><defName>RWMT_CRendered</defName>'
            f'<official>{str(official).lower()}</official>{items("recipes", recipes)}{items("things", THINGS)}'
            '</RWMT.CRendered.ConfigDef></Defs>')


def launch_official(root, display, shots):
    """Child of the supervisor: private Xvfb display, official process, periodic private screenshots."""
    root = root.resolve()
    if root == REPO or REPO in root.parents or not (root/'RimWorld').is_file() or not 1 <= display <= 999:
        raise ValueError('invalid official research root')
    if not LVP_ICD.is_file() or not shutil.which('Xvfb'):
        raise ValueError('Xvfb and Mesa lavapipe are required')
    runtime = root/'runtime'; runtime.mkdir(mode=0o700)
    socket = Path(f'/tmp/.X11-unix/X{display}')
    if socket.exists():
        raise ValueError('virtual display number already in use')
    xvfb = subprocess.Popen(['Xvfb', f':{display}', '-screen', '0', '1600x900x24', '-nolisten', 'tcp'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(200):
            if socket.exists(): break
            time.sleep(.05)
        else:
            raise RuntimeError('virtual display did not start')
        env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(root/'home'),
               'XDG_CONFIG_HOME': str(root/'xdg'), 'XDG_RUNTIME_DIR': str(runtime), 'LANG': 'C.UTF-8',
               'DISPLAY': f':{display}', 'VK_ICD_FILENAMES': str(LVP_ICD)}
        game = subprocess.Popen(['./RimWorld', '-NoCrashDialog'], cwd=root, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        taken = 0
        while game.poll() is None:
            if shots is not None and taken < 150 and shutil.which('import'):
                subprocess.run(['import', '-display', f':{display}', '-window', 'root', str(shots/f'{taken:03}.png')],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, env={'PATH': env['PATH']})
                taken += 1
            time.sleep(2)
        return game.returncode
    finally:
        xvfb.terminate()
        try: xvfb.wait(10)
        except subprocess.TimeoutExpired: xvfb.kill(); xvfb.wait()


def build(dest, snapshot, harmony, out):
    process = pv.run_command(['dotnet', 'build', str(REPO/'tests/fixtures/validation-mods-src/CRendered'),
        '-c', 'Release', '-o', str(dest), f'-p:GameManagedDir={snapshot/"game"}',
        f'-p:HarmonyDll={harmony}', '--nologo'], out/'CRendered-build.log', timeout=180, memory_limit=2*1024**3)
    if process['exitCode'] != 0 or process['interrupted']:
        raise RuntimeError('observer build failed')


def official_root(snapshot, target, out, name, recipes):
    """Same Mods, ModsConfig and Prefs as the product's target run; only the observer config differs."""
    root = out/name; root.mkdir()
    game = snapshot/'game'
    for entry in game.iterdir():
        if entry.name not in ('RimWorld', 'Data'):
            (root/entry.name).symlink_to(entry)
    shutil.copyfile(game/'RimWorld', root/'RimWorld'); (root/'RimWorld').chmod(0o700)
    (root/'Data').mkdir(); (root/'Data/Core').symlink_to(game/'Data/Core')
    shutil.copytree(target/'host/Mods', root/'Mods')
    configs = list((root/'Mods').glob('*/Defs/CRendered.xml'))
    if len(configs) != 1:
        raise ValueError('private observer configuration missing')
    configs[0].write_text(config(True, recipes))
    conf = root/'xdg/unity3d/Ludeon Studios/RimWorld by Ludeon Studios/Config'
    conf.mkdir(parents=True)
    for file in ('ModsConfig.xml', 'Prefs.xml'):
        shutil.copyfile(target/'userdata/Config'/file, conf/file)
    (root/'home').mkdir()
    return root, conf.parent/'Logs/Player.log'


def read_official(log, process):
    rows, errors = [], []
    if log.is_file() and log.stat().st_size <= 8*1024**2:
        for line in log.read_text(encoding='utf-8', errors='replace').splitlines():
            match = LOG.match(line)
            if match and match[1] in ('ERROR', 'WARN'):
                errors.append(match[3])
            if MARKER in line:
                try: rows.append(json.loads(line.split(MARKER, 1)[1]))
                except ValueError: errors.append('invalid observer JSON')
    else:
        errors.append('missing or oversized log')
    return {'rows': rows, 'errors': errors, 'exitCode': process.get('exitCode'),
            'interrupted': process.get('interrupted') is not False, 'seconds': process.get('seconds')}


def run_official(args, out, product_target, name, recipes, display):
    root, player_log = official_root(args.snapshot, product_target, out, name, recipes)
    shots = out/(name + '-screens'); shots.mkdir(mode=0o700)
    process = pv.run_command([sys.executable, str(Path(__file__).resolve()), '--official-root', str(root),
        '--display', str(display), '--shots', str(shots)], out/(name + '-stdout.log'),
        timeout=480, memory_limit=6*1024**3, watch_paths=(player_log,))
    return read_official(player_log, process)


def trace_of(official):
    rows = official.get('rows') if isinstance(official, dict) else None
    return rows[0] if isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict) else None


def official_case(trace, recipe):
    cases = [c for c in (trace or {}).get('cases', []) if isinstance(c, dict) and c.get('recipe') == recipe]
    return cases[0] if len(cases) == 1 else None


def case_drawn(case):
    """The real dialog drew its ingredient pane in enough real Repaint passes, cleanly."""
    pane = case.get('pane') if isinstance(case, dict) else None
    return (isinstance(pane, dict) and case.get('setup') == 'open' and case.get('opened') is True
            and case.get('openedOnMainThread') is True and case.get('freshGameKept') is True
            and case.get('removed') is True and case.get('exception') is False
            and type(case.get('paneRepaints')) is int and case['paneRepaints'] >= MIN_PANE_REPAINTS
            and pane.get(str(REPAINT)) == case['paneRepaints'] and type(case.get('ui')) is int
            and type(case.get('listing')) is int and case['ui'] == case['listing'] == sum(pane.values()))


def compare(product_rows, official):
    """Line up the product's non-rendered answer with the rows the real dialog listed."""
    trace = trace_of(official)
    out = []
    for recipe, thing, expected_visible, expected_allowed in ROWS:
        matches = [r for r in product_rows if isinstance(r, dict) and isinstance(r.get('expected'), dict)
                   and r['expected'].get('recipe') == recipe and r['expected'].get('thing') == thing]
        actual = matches[0].get('actual') if len(matches) == 1 and isinstance(matches[0].get('actual'), dict) else {}
        row = {'recipe': recipe, 'thing': thing, 'expectedVisible': expected_visible, 'expectedAllowed': expected_allowed,
               'productVisible': actual.get('visible'), 'productAllowed': actual.get('allowed'),
               'productOutcome': matches[0].get('outcome') if len(matches) == 1 else None}
        case = official_case(trace, recipe)
        listed = (case or {}).get('listed') if isinstance((case or {}).get('listed'), dict) else {}
        types = listed.get(thing)
        allowed = (case or {}).get('allowed') if isinstance((case or {}).get('allowed'), dict) else {}
        observed = case is not None and case_drawn(case) and isinstance(types, list) and type(allowed.get(thing)) is bool
        on_repaint = observed and REPAINT in types
        row.update(officialObserved=observed, officialListedOnRepaint=on_repaint if observed else None,
                   # A row listed only in some passes of one kind would make the reference ambiguous.
                   officialListingConsistent=observed and (set(types) in (set(), {REPAINT, LAYOUT})),
                   officialAllowed=allowed.get(thing) if observed else None)
        row['visibleAgrees'] = observed and type(row['productVisible']) is bool and row['productVisible'] is on_repaint
        row['allowedAgrees'] = observed and type(row['productAllowed']) is bool and row['productAllowed'] is row['officialAllowed']
        out.append(row)
    return out


def gate(product, control, observer, rows):
    """Every condition must hold for the rendered reference to agree. Never a qualification."""
    reasons = {r.get('code') for r in product.get('reasons', []) if isinstance(r, dict)}
    observer_trace, control_trace = trace_of(observer), trace_of(control)
    checks = {
        'productCompleted': (product.get('executionStatus') == 'completed'
                             and (product.get('stages') or {}).get('C', {}).get('status') == 'completed'
                             and reasons == PRODUCT_REASONS),
        'officialCompleted': all(o.get('exitCode') == 0 and o.get('interrupted') is False and t is not None
                                 and t.get('stop') == 'none' for o, t in ((control, control_trace), (observer, observer_trace))),
        'controlOpenedNothing': control_trace is not None and control_trace.get('cases') == [],
        'dialogsDrawn': (observer_trace is not None and len(observer_trace.get('cases') or []) == len(RECIPES)
                         and all(case_drawn(official_case(observer_trace, r)) for r in RECIPES)),
        'diagnosticsMatchControl': (classify(observer.get('errors', [])) == classify(control.get('errors', []))
                                    and classify(observer.get('errors', []))['billDialogWindowException'] == 0
                                    and classify(observer.get('errors', []))['other'] == 0),
        'rowsAgree': len(rows) == len(ROWS) and all(r['visibleAgrees'] and r['allowedAgrees']
                                                    and r['officialListingConsistent'] for r in rows),
    }
    return {'checks': checks, 'agreement': all(checks.values()), 'qualified': False}


def official_summary(official):
    trace = trace_of(official) or {}
    return {'exitCode': official.get('exitCode'), 'interrupted': official.get('interrupted'),
            'seconds': official.get('seconds'), 'traceRows': len(official.get('rows', [])),
            'stop': trace.get('stop'), 'totalRepaints': trace.get('totalRepaints'),
            'drainRepaints': trace.get('drainRepaints'), 'lateContents': trace.get('lateContents'),
            'diagnosticCount': len(official.get('errors', [])), 'diagnostics': classify(official.get('errors', [])),
            'cases': [{k: c.get(k) for k in CASE_KEYS} for c in trace.get('cases', []) if isinstance(c, dict)]}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--worker', type=Path, default=REPO/'worker/bin')
    p.add_argument('--harmony-dll', type=Path)
    p.add_argument('--official-root', type=Path)
    p.add_argument('--display', type=int, default=77)
    p.add_argument('--shots', type=Path)
    a = p.parse_args(argv)
    if a.official_root is not None:
        return launch_official(a.official_root, a.display, a.shots)
    if any(x is None for x in (a.out, a.snapshot, a.harmony_dll)):
        p.error('snapshot, out and harmony-dll required')
    a.out = a.out.resolve(); a.snapshot = a.snapshot.resolve(); a.harmony_dll = a.harmony_dll.resolve()
    if a.out.exists() or a.out == REPO or REPO in a.out.parents:
        p.error('out must be new and outside checkout')
    a.out.mkdir(parents=True, mode=0o700)
    fixtures = a.out/'fixtures'; fixtures.mkdir()
    names = ('harmonylib', 'crendered', 'billingredients')
    for name in names:
        shutil.copytree(REPO/'tests/fixtures/validation-mods'/name, fixtures/name)
    (fixtures/'harmonylib/Assemblies').mkdir(exist_ok=True)
    shutil.copyfile(a.harmony_dll, fixtures/'harmonylib/Assemblies/0Harmony.dll')
    build(fixtures/'crendered/Assemblies', a.snapshot, a.harmony_dll, a.out)
    (fixtures/'crendered/Defs').mkdir()
    (fixtures/'crendered/Defs/CRendered.xml').write_text(config(False))
    request = {'recordType': 'modValidationRequest', 'schemaVersion': 1, 'levels': ['A', 'C'],
        'mods': [{'path': str(fixtures/n), 'target': n == names[-1]} for n in names],
        'tests': ['bill-ingredient-options.v1'],
        'expectations': {'billIngredients': [dict(recipe=r, thing=t, visible=v, allowed=al) for r, t, v, al in ROWS]},
        'limits': {'timeoutSeconds': 180, 'memoryMiB': 2048, 'logMiB': 8}}
    (a.out/'request.json').write_text(json.dumps(request))
    product = vh.run_validation(a.snapshot, a.out/'request.json', a.out/'product', a.worker, keep_run_dirs=True)
    product_rows = (product.get('checks') or {}).get('billIngredients') or []
    target = a.out/'product/target'
    control = run_official(a, a.out, target, 'official-control', (), a.display)
    observer = run_official(a, a.out, target, 'official-observer', RECIPES, a.display)
    pv.write_json(a.out/'private-evidence.json', {'product': product, 'control': control, 'observer': observer})
    rows = compare(product_rows, observer)
    summary = {'schemaVersion': 1, 'research': 'c-rendered-dialog',
               'product': {'status': product.get('status'), 'executionStatus': product.get('executionStatus'),
                           'stageC': (product.get('stages') or {}).get('C', {}).get('status'),
                           'reasons': sorted(r.get('code') for r in product.get('reasons', []) if isinstance(r, dict))},
               'officialControl': official_summary(control), 'officialObserver': official_summary(observer),
               'rows': rows, **gate(product, control, observer, rows)}
    pv.write_json(a.out/'safe-summary.json', summary)
    print(json.dumps(summary, indent=1))
    return 0 if summary['agreement'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
