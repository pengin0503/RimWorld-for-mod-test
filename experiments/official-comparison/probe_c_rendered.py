"""Development-only research: the real bill dialog in a *rendering* official process.

Follow-up to the C0 material stop (official headless has no OnGUI pass). One invocation
runs the product's non-rendered bill-ingredient-options.v1 case once, then two official
processes that render to a private virtual display (Xvfb + Mesa lavapipe):

* control: the observer is loaded but opens no dialog (rendering-path diagnostics only);
* observer: the real Dialog_BillConfig is opened through the real WindowStack at the
  Entry state and the ingredient rows that the dialog's own code listed are recorded.

The rows are lined up with the product's answer. A comparison spec (``--spec``) names the
rows; without one the self-made fixture rows are used. ``--request`` takes a product
request made by ``codex_workflow.py fetch-mods`` (real MODs, including the Harmony MOD);
the observer is added after Harmony. With ``expand`` the observer first records the
dialog in its default tree state and then opens the category paths of the spec's things
with the game's own ``TreeNode.SetOpen`` (what the expand button does); the expanded
listing is compared.

This never grants C qualification, never changes product predicates or caches and is not
part of the product flow. No input event is synthesized; the official processes quit by
themselves. Game files, raw logs and screenshots stay in the private --out directory.
"""
import argparse
from collections import Counter
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
# A real MOD's product answer may differ from the request's expectation; that is a result to
# compare, not a failed run. Only this reason (and the C stage failure it causes) is allowed.
MISMATCH_REASON = 'billIngredientMismatch'
MIN_PANE_REPAINTS = 3
# Dialog_BillConfig passes openMask 4 to ThingFilterUI in 1.7.4985 rev1269.
OPEN_MASK = 4
HARMONY_MOD = 'brrainz.harmony'
FIXTURE_HARMONY = 'rwmodtest.harmonylib'
NAME = re.compile(r'[A-Za-z0-9_]{1,64}')
SPEC_NAME = re.compile(r'[A-Za-z0-9_.-]{1,64}')
MAX_ROWS = 400
CREDENTIAL_ENV = ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'AWS_PROFILE',
                  'AWS_DEFAULT_PROFILE', 'R2_ENDPOINT', 'R2_BUCKET')
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
             'paneRepaints', 'rowCount', 'exception', 'exceptionKind', 'expanded', 'restored',
             'openedCategories', 'categories')


def load_spec(value):
    """Validate a comparison spec and return it normalized (rows as tuples, unique recipes/things in order)."""
    if not isinstance(value, dict) or set(value) - {'name', 'expand', 'allowProductMismatch', 'rows'}:
        raise ValueError('invalid comparison spec')
    name, expand, mismatch = value.get('name', 'custom'), value.get('expand', False), value.get('allowProductMismatch', False)
    rows = value.get('rows')
    if (not isinstance(name, str) or not SPEC_NAME.fullmatch(name) or type(expand) is not bool or type(mismatch) is not bool
            or not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS):
        raise ValueError('invalid comparison spec')
    out = []
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'recipe', 'thing', 'visible', 'allowed'}
                or any(not isinstance(row[k], str) or not NAME.fullmatch(row[k]) for k in ('recipe', 'thing'))
                or any(type(row[k]) is not bool for k in ('visible', 'allowed'))):
            raise ValueError('invalid comparison row')
        out.append((row['recipe'], row['thing'], row['visible'], row['allowed']))
    if len({(r, t) for r, t, _, _ in out}) != len(out):
        raise ValueError('duplicate comparison row')
    return {'name': name, 'expand': expand, 'allowProductMismatch': mismatch, 'rows': tuple(out),
            'recipes': tuple(dict.fromkeys(r for r, _, _, _ in out)), 'things': tuple(dict.fromkeys(t for _, t, _, _ in out))}


FIXTURE_SPEC = load_spec({'name': 'fixture', 'rows': [dict(recipe=r, thing=t, visible=v, allowed=a) for r, t, v, a in ROWS]})


def classify(messages):
    counts = {name: 0 for name, _ in DIAGNOSTIC_CLASSES}
    counts['other'] = 0
    for message in messages:
        name = next((n for n, rx in DIAGNOSTIC_CLASSES if isinstance(message, str) and rx.match(message)), 'other')
        counts[name] += 1
    return counts


def diagnostic_multiset(messages):
    """Known classes by name (their text varies, e.g. timings); anything else by its exact private text."""
    return Counter(next((n for n, rx in DIAGNOSTIC_CLASSES if isinstance(m, str) and rx.match(m)), None) or repr(m)
                   for m in messages)


def config(official, recipes=RECIPES, things=THINGS, expand=False):
    if (type(official) is not bool or type(expand) is not bool
            or any(not isinstance(n, str) or not NAME.fullmatch(n) for n in (*recipes, *things))):
        raise ValueError('invalid observer configuration')
    items = lambda tag, names: f'<{tag}>' + ''.join(f'<li>{n}</li>' for n in names) + f'</{tag}>'
    return ('<Defs><RWMT.CRendered.ConfigDef><defName>RWMT_CRendered</defName>'
            f'<official>{str(official).lower()}</official><expand>{str(expand).lower()}</expand>'
            f'<openMask>{OPEN_MASK}</openMask>{items("recipes", recipes)}{items("things", things)}'
            '</RWMT.CRendered.ConfigDef></Defs>')


def observer_about(harmony_package):
    """About.xml of the observer: it depends on, and loads after, the Harmony that the run provides."""
    if harmony_package not in (HARMONY_MOD, FIXTURE_HARMONY):
        raise ValueError('unsupported Harmony provider')
    return ('<ModMetaData><name>RWMT development rendered bill dialog observer</name>'
            '<author>RimWorld-for-mod-test fixtures</author><packageId>rwmodtest.crendered</packageId>'
            '<description>Finite development-only research: records which ingredient rows the real bill dialog lists '
            'in a rendering official process. Does not grant qualification.</description>'
            '<supportedVersions><li>1.7</li></supportedVersions>'
            f'<modDependencies><li><packageId>{harmony_package}</packageId><displayName>Harmony</displayName>'
            '<downloadUrl>https://github.com/pengin0503/RimWorld-for-mod-test</downloadUrl></li></modDependencies>'
            f'<loadAfter><li>{harmony_package}</li></loadAfter></ModMetaData>')


def limits():
    return {'timeoutSeconds': 300, 'memoryMiB': 4096, 'logMiB': 8}


def expectations(spec):
    return {'billIngredients': [dict(recipe=r, thing=t, visible=v, allowed=a) for r, t, v, a in spec['rows']]}


def fixture_request(fixtures, names, spec):
    return {'recordType': 'modValidationRequest', 'schemaVersion': 1, 'levels': ['A', 'C'],
            'mods': [{'path': str(fixtures/n), 'target': n == names[-1]} for n in names],
            'tests': ['bill-ingredient-options.v1'], 'expectations': expectations(spec), 'limits': limits()}


def real_request(base, observer, spec):
    """The fetch-mods request with the observer inserted right after the Harmony MOD."""
    mods = base.get('mods') if isinstance(base, dict) else None
    if (not isinstance(mods, list) or not mods or any(not isinstance(m, dict) or not isinstance(m.get('path'), str) for m in mods)
            or not any(m.get('target') is True for m in mods)):
        raise ValueError('invalid base request')
    harmony = [i for i, m in enumerate(mods) if str(m.get('packageId', '')).casefold() == HARMONY_MOD]
    if len(harmony) != 1 or any('crendered' in str(m.get('packageId', '')).casefold() for m in mods):
        raise ValueError('base request needs exactly one Harmony MOD and no observer')
    mods = [dict(m) for m in mods]
    mods.insert(harmony[0] + 1, {'path': str(observer), 'target': False})
    request = {'recordType': 'modValidationRequest', 'schemaVersion': 1, 'levels': ['A', 'C'],
               'mods': mods, 'tests': ['bill-ingredient-options.v1'], 'expectations': expectations(spec), 'limits': limits()}
    for key in ('official', 'language'):
        if key in base:
            request[key] = base[key]
    return request


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
            if shots is not None and taken < 200 and shutil.which('import'):
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


def official_root(snapshot, target, out, name, spec, recipes, official_content=('Core',)):
    """Same Mods, ModsConfig and Prefs as the product's target run; only the observer config differs."""
    root = out/name; root.mkdir()
    game = snapshot/'game'
    for entry in game.iterdir():
        if entry.name not in ('RimWorld', 'Data'):
            (root/entry.name).symlink_to(entry)
    shutil.copyfile(game/'RimWorld', root/'RimWorld'); (root/'RimWorld').chmod(0o700)
    (root/'Data').mkdir()
    for content in official_content:
        if not isinstance(content, str) or not NAME.fullmatch(content) or not (game/'Data'/content).is_dir():
            raise ValueError('official content missing from the snapshot')
        (root/'Data'/content).symlink_to(game/'Data'/content)
    shutil.copytree(target/'host/Mods', root/'Mods')
    configs = list((root/'Mods').glob('*/Defs/CRendered.xml'))
    if len(configs) != 1:
        raise ValueError('private observer configuration missing')
    configs[0].write_text(config(True, recipes, spec['things'], spec['expand']))
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


def run_official(args, out, product_target, name, spec, recipes, official_content):
    root, player_log = official_root(args.snapshot, product_target, out, name, spec, recipes, official_content)
    shots = out/(name + '-screens'); shots.mkdir(mode=0o700)
    process = pv.run_command([sys.executable, str(Path(__file__).resolve()), '--official-root', str(root),
        '--display', str(args.display), '--shots', str(shots)], out/(name + '-stdout.log'),
        timeout=600, memory_limit=6*1024**3, watch_paths=(player_log,))
    return read_official(player_log, process)


def trace_of(official):
    rows = official.get('rows') if isinstance(official, dict) else None
    return rows[0] if isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict) else None


def official_case(trace, recipe):
    cases = [c for c in (trace or {}).get('cases', []) if isinstance(c, dict) and c.get('recipe') == recipe]
    return cases[0] if len(cases) == 1 else None


def stage_drawn(stage):
    """One stage of a dialog drew its ingredient pane in enough real Repaint passes."""
    pane = stage.get('pane') if isinstance(stage, dict) else None
    return (isinstance(pane, dict) and type(stage.get('paneRepaints')) is int and stage['paneRepaints'] >= MIN_PANE_REPAINTS
            and pane.get(str(REPAINT)) == stage['paneRepaints'] and type(stage.get('ui')) is int
            and type(stage.get('listing')) is int and stage['ui'] == stage['listing'] == sum(pane.values()))


def case_drawn(case, expand=False):
    """The real dialog drew cleanly; with expansion, both stages drew and the tree was restored."""
    if not isinstance(case, dict) or not stage_drawn(case):
        return False
    clean = (case.get('setup') == 'open' and case.get('opened') is True and case.get('openedOnMainThread') is True
             and case.get('freshGameKept') is True and case.get('removed') is True and case.get('exception') is False)
    if not expand:
        return clean and not case.get('expanded') and not case.get('initial')
    return (clean and case.get('expanded') is True and case.get('restored') is True
            and isinstance(case.get('openedCategories'), list) and stage_drawn(case.get('initial')))


def listing_of(stage, thing):
    listed = stage.get('listed') if isinstance(stage, dict) and isinstance(stage.get('listed'), dict) else {}
    types = listed.get(thing)
    return types if isinstance(types, list) else None


def compare(product_rows, official, spec=FIXTURE_SPEC):
    """Line up the product's non-rendered answer with the rows the real dialog listed."""
    trace = trace_of(official)
    out = []
    for recipe, thing, expected_visible, expected_allowed in spec['rows']:
        matches = [r for r in product_rows if isinstance(r, dict) and isinstance(r.get('expected'), dict)
                   and r['expected'].get('recipe') == recipe and r['expected'].get('thing') == thing]
        actual = matches[0].get('actual') if len(matches) == 1 and isinstance(matches[0].get('actual'), dict) else {}
        row = {'recipe': recipe, 'thing': thing, 'expectedVisible': expected_visible, 'expectedAllowed': expected_allowed,
               'productVisible': actual.get('visible'), 'productAllowed': actual.get('allowed'),
               'productOutcome': matches[0].get('outcome') if len(matches) == 1 else None}
        case = official_case(trace, recipe)
        types = listing_of(case, thing)
        allowed = (case or {}).get('allowed') if isinstance((case or {}).get('allowed'), dict) else {}
        observed = (case is not None and case_drawn(case, spec['expand']) and types is not None
                    and type(allowed.get(thing)) is bool)
        on_repaint = observed and REPAINT in types
        row.update(officialObserved=observed, officialListedOnRepaint=on_repaint if observed else None,
                   # A row listed only in some passes of one kind would make the reference ambiguous.
                   officialListingConsistent=observed and (set(types) in (set(), {REPAINT, LAYOUT})),
                   officialAllowed=allowed.get(thing) if observed else None)
        if spec['expand']:
            initial = listing_of((case or {}).get('initial'), thing) if observed else None
            # Recorded only: the default tree state is a fact about the dialog, not the compared answer.
            row['officialListedInitially'] = (REPAINT in initial) if initial is not None else None
        row['visibleAgrees'] = observed and type(row['productVisible']) is bool and row['productVisible'] is on_repaint
        row['allowedAgrees'] = observed and type(row['productAllowed']) is bool and row['productAllowed'] is row['officialAllowed']
        out.append(row)
    return out


def gate(product, control, observer, rows, spec=FIXTURE_SPEC):
    """Every condition must hold for the rendered reference to agree. Never a qualification."""
    reasons = {r.get('code') for r in product.get('reasons', []) if isinstance(r, dict)}
    allowed_reasons = PRODUCT_REASONS | ({MISMATCH_REASON} if spec['allowProductMismatch'] else set())
    stage_c = (product.get('stages') or {}).get('C', {}).get('status')
    observer_trace, control_trace = trace_of(observer), trace_of(control)
    observer_errors, control_errors = observer.get('errors', []), control.get('errors', [])
    checks = {
        'productCompleted': (product.get('executionStatus') == 'completed'
                             and (stage_c == 'completed' or (stage_c == 'failed' and spec['allowProductMismatch']
                                                             and MISMATCH_REASON in reasons))
                             and PRODUCT_REASONS <= reasons <= allowed_reasons),
        'officialCompleted': all(o.get('exitCode') == 0 and o.get('interrupted') is False and t is not None
                                 and t.get('stop') == 'none' for o, t in ((control, control_trace), (observer, observer_trace))),
        'controlOpenedNothing': control_trace is not None and control_trace.get('cases') == [],
        'dialogsDrawn': (observer_trace is not None and observer_trace.get('expand', False) is spec['expand']
                         and len(observer_trace.get('cases') or []) == len(spec['recipes'])
                         and all(case_drawn(official_case(observer_trace, r), spec['expand']) for r in spec['recipes'])),
        'diagnosticsMatchControl': (diagnostic_multiset(observer_errors) == diagnostic_multiset(control_errors)
                                    and classify(observer_errors)['billDialogWindowException'] == 0),
        'rowsAgree': len(rows) == len(spec['rows']) and all(r['visibleAgrees'] and r['allowedAgrees']
                                                            and r['officialListingConsistent'] for r in rows),
    }
    return {'checks': checks, 'agreement': all(checks.values()), 'qualified': False}


def official_summary(official):
    trace = trace_of(official) or {}
    cases = []
    for c in trace.get('cases', []):
        if not isinstance(c, dict):
            continue
        item = {k: c.get(k) for k in CASE_KEYS}
        if isinstance(c.get('initial'), dict):
            item['initial'] = {k: c['initial'].get(k) for k in ('pane', 'ui', 'listing', 'paneRepaints', 'rowCount', 'categories')}
        cases.append(item)
    errors = official.get('errors', [])
    return {'exitCode': official.get('exitCode'), 'interrupted': official.get('interrupted'),
            'seconds': official.get('seconds'), 'traceRows': len(official.get('rows', [])),
            'stop': trace.get('stop'), 'expand': trace.get('expand'), 'totalRepaints': trace.get('totalRepaints'),
            'drainRepaints': trace.get('drainRepaints'), 'lateContents': trace.get('lateContents'),
            'diagnosticCount': len(errors), 'diagnostics': classify(errors),
            'distinctOtherDiagnostics': len({m for m in errors if classify([m])['other']}), 'cases': cases}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--worker', type=Path, default=REPO/'worker/bin')
    p.add_argument('--harmony-dll', type=Path)
    p.add_argument('--spec', type=Path, help='comparison spec JSON (default: the self-made fixture rows)')
    p.add_argument('--request', type=Path, help='fetch-mods request with real MODs (default: self-made fixtures)')
    p.add_argument('--expand', action='store_true', help='compare after opening the things\' category paths')
    p.add_argument('--official-root', type=Path)
    p.add_argument('--display', type=int, default=77)
    p.add_argument('--shots', type=Path)
    a = p.parse_args(argv)
    if a.official_root is not None:
        return launch_official(a.official_root, a.display, a.shots)
    if any(x is None for x in (a.out, a.snapshot, a.harmony_dll)):
        p.error('snapshot, out and harmony-dll required')
    try:
        spec = load_spec(json.loads(a.spec.read_text(encoding='utf-8'))) if a.spec else FIXTURE_SPEC
        base = json.loads(a.request.read_text(encoding='utf-8')) if a.request else None
    except (OSError, ValueError) as error:
        p.error(f'invalid spec or request: {error}')
    if a.expand:
        spec = dict(spec, expand=True)
    a.out = a.out.resolve(); a.snapshot = a.snapshot.resolve(); a.harmony_dll = a.harmony_dll.resolve()
    if a.out.exists() or a.out == REPO or REPO in a.out.parents:
        p.error('out must be new and outside checkout')
    # Real MOD DLLs run below; nothing here needs storage credentials.
    for name in CREDENTIAL_ENV:
        os.environ.pop(name, None)
    a.out.mkdir(parents=True, mode=0o700)
    fixtures = a.out/'fixtures'; fixtures.mkdir()
    shutil.copytree(REPO/'tests/fixtures/validation-mods/crendered', fixtures/'crendered')
    observer = fixtures/'crendered'
    names = ('harmonylib', 'crendered', 'billingredients')
    if base is None:
        for name in ('harmonylib', 'billingredients'):
            shutil.copytree(REPO/'tests/fixtures/validation-mods'/name, fixtures/name)
        (fixtures/'harmonylib/Assemblies').mkdir(exist_ok=True)
        shutil.copyfile(a.harmony_dll, fixtures/'harmonylib/Assemblies/0Harmony.dll')
    else:
        (observer/'About/About.xml').write_text(observer_about(HARMONY_MOD))
    build(observer/'Assemblies', a.snapshot, a.harmony_dll, a.out)
    (observer/'Defs').mkdir()
    (observer/'Defs/CRendered.xml').write_text(config(False, spec['recipes'], spec['things'], spec['expand']))
    try:
        request = fixture_request(fixtures, names, spec) if base is None else real_request(base, observer, spec)
    except ValueError as error:
        p.error(str(error))
    official_content = tuple(request.get('official') or ('Core',))
    (a.out/'request.json').write_text(json.dumps(request))
    product = vh.run_validation(a.snapshot, a.out/'request.json', a.out/'product', a.worker, keep_run_dirs=True)
    product_rows = (product.get('checks') or {}).get('billIngredients') or []
    target = a.out/'product/target'
    control = run_official(a, a.out, target, 'official-control', spec, (), official_content)
    observed = run_official(a, a.out, target, 'official-observer', spec, spec['recipes'], official_content)
    pv.write_json(a.out/'private-evidence.json', {'product': product, 'control': control, 'observer': observed})
    rows = compare(product_rows, observed, spec)
    summary = {'schemaVersion': 2, 'research': 'c-rendered-dialog',
               'spec': {'name': spec['name'], 'expand': spec['expand'], 'allowProductMismatch': spec['allowProductMismatch'],
                        'rows': len(spec['rows'])},
               'product': {'status': product.get('status'), 'executionStatus': product.get('executionStatus'),
                           'stageC': (product.get('stages') or {}).get('C', {}).get('status'),
                           'reasons': sorted(r.get('code') for r in product.get('reasons', []) if isinstance(r, dict)),
                           'mods': [m.get('packageId') for m in product.get('mods', []) if isinstance(m, dict)]},
               'officialControl': official_summary(control), 'officialObserver': official_summary(observed),
               'rows': rows, **gate(product, control, observed, rows, spec)}
    pv.write_json(a.out/'safe-summary.json', summary)
    print(json.dumps(summary, indent=1))
    return 0 if summary['agreement'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
