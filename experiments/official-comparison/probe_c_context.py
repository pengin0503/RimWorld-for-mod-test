"""Development-only C0 context research. Never grants qualification."""
import argparse
import json
import os
import re
from pathlib import Path
import shutil
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from tools import validation_host as vh
from tools import private_validation as pv
from tools import c_context_evidence as evidence


class FixtureBuildFailure(RuntimeError):
    def __init__(self, diagnostics):
        self.diagnostics = diagnostics


def build_diagnostics(text):
    rows = []
    for source, line, code in re.findall(r'(CContext|MapProbe|EventChoice)\.cs\(([0-9]+),[0-9]+\): error (CS[0-9]{4})\b', text):
        row = {'source': source, 'line': int(line), 'code': code}
        if 1 <= row['line'] <= 10000 and row not in rows:
            rows.append(row)
        if len(rows) == 16: break
    return rows


def config(mode, official):
    if mode not in ('material', 'event') or type(official) is not bool:
        raise ValueError('unsupported context mode')
    return ('<Defs><RWMT.CContext.ConfigDef><defName>RWMT_CContext</defName>'
            f'<mode>{mode}</mode><official>{str(official).lower()}</official>'
            '</RWMT.CContext.ConfigDef></Defs>')


def launch_official(root, mode):
    root = root.resolve()
    if root == REPO or REPO in root.parents or not (root/'RimWorld').is_file():
        raise ValueError('invalid official research root')
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(root/'home'),
           'XDG_CONFIG_HOME': str(root/'xdg'), 'LANG': 'C.UTF-8'}
    os.chdir(root)
    args = ['./RimWorld', '-headless', '-NoCrashDialog', '-quicktest' if mode == 'event' else '-QuitAfterBoot']
    os.execve('./RimWorld', args, env)


def build(project, dest, snapshot, harmony, out):
    process = pv.run_command(['dotnet', 'build', str(REPO/'tests/fixtures/validation-mods-src'/project),
        '-c', 'Release', '-o', str(dest), f'-p:GameManagedDir={snapshot/"game"}',
        f'-p:HarmonyDll={harmony}', '--nologo'], out/(project+'-build.log'), timeout=120, memory_limit=2*1024**3)
    if process['exitCode'] != 0 or process['interrupted']:
        log = out/(project+'-build.log')
        text = log.read_text(errors='replace') if log.is_file() and log.stat().st_size <= 8*1024**2 else ''
        raise FixtureBuildFailure(build_diagnostics(text))


def read_evidence(path, process, *, worker):
    if not path.is_file() or path.stat().st_size > 8*1024**2:
        parsed = {'rows': [], 'errors': ['missing or oversized log']}
    else:
        parsed = evidence.parse_lines(path.read_text(encoding='utf-8', errors='replace').splitlines(), worker=worker)
    return {**parsed, 'exitCode': process.get('exitCode'), 'interrupted': process.get('interrupted') is not False}


def product_evidence(result, log):
    process = result.get('process', {}).get('target', {})
    return read_evidence(log, {**process, 'interrupted': result.get('executionStatus') != 'completed'}, worker=True)


def product_ready(result):
    codes = {r.get('code') for r in result.get('reasons', []) if isinstance(r, dict)}
    return (result.get('executionStatus') == 'completed'
            and result.get('stages', {}).get('C', {}).get('status') == 'completed'
            and type(result.get('process', {}).get('target', {}).get('exitCode')) is int
            and result['process']['target']['exitCode'] == 0
            and codes <= {'experimental', 'cNotQualified', 'mapNotQualified'})


def official_root(snapshot, target, out, mode):
    root = out/'official'; root.mkdir()
    game = snapshot/'game'
    for entry in game.iterdir():
        if entry.name not in ('RimWorld', 'Data'):
            (root/entry.name).symlink_to(entry)
    shutil.copyfile(game/'RimWorld', root/'RimWorld'); (root/'RimWorld').chmod(0o700)
    (root/'Data').mkdir(); (root/'Data/Core').symlink_to(game/'Data/Core')
    shutil.copytree(target/'host/Mods', root/'Mods')
    configs = list((root/'Mods').glob('*/Defs/CContext.xml'))
    if len(configs) != 1:
        raise ValueError('private observer configuration missing')
    configs[0].write_text(config(mode, True))
    conf = root/'xdg/unity3d/Ludeon Studios/RimWorld by Ludeon Studios/Config'
    conf.mkdir(parents=True)
    for name in ('ModsConfig.xml', 'Prefs.xml'):
        shutil.copyfile(target/'userdata/Config'/name, conf/name)
    (root/'home').mkdir()
    return root, conf.parent/'Logs/Player.log'


def run_case(mode, args):
    out = args.out/mode; out.mkdir()
    fixtures = out/'fixtures'; fixtures.mkdir()
    names = ('harmonylib', 'ccontext', 'mapprobe', 'eventchoice') if mode == 'event' else ('harmonylib', 'ccontext', 'billingredients')
    for name in names:
        shutil.copytree(REPO/'tests/fixtures/validation-mods'/name, fixtures/name)
    (fixtures/'harmonylib/Assemblies').mkdir(exist_ok=True)
    shutil.copyfile(args.harmony_dll, fixtures/'harmonylib/Assemblies/0Harmony.dll')
    for name, project in [('ccontext', 'CContext'), *([('mapprobe', 'MapProbe'), ('eventchoice', 'EventChoice')] if mode == 'event' else [])]:
        build(project, fixtures/name/'Assemblies', args.snapshot, args.harmony_dll, out)
    (fixtures/'ccontext/Defs').mkdir()
    (fixtures/'ccontext/Defs/CContext.xml').write_text(config(mode, False))
    request = {'recordType': 'modValidationRequest', 'schemaVersion': 1, 'levels': ['A', 'C'],
        'mods': [{'path': str(fixtures/name), 'target': name == names[-1]} for name in names],
        'tests': ['event-choice.v1' if mode == 'event' else 'bill-ingredient-options.v1'],
        'expectations': {'eventChoices': [{'event': 'RWMT_ChoiceEvent', 'choice': 'accept', 'rewardThing': 'Steel', 'rewardCount': 10}]} if mode == 'event'
            else {'billIngredients': [{'recipe': 'RWMT_BillOptions', 'thing': 'RWMT_BillGrain', 'visible': True, 'allowed': True}]},
        'limits': {'timeoutSeconds': 180, 'memoryMiB': 2048, 'logMiB': 8}}
    if mode == 'event': request['map'] = {'seed': 'rwmt'}
    path = out/'request.json'; path.write_text(json.dumps(request))
    result = vh.run_validation(args.snapshot, path, out/'product', args.worker, keep_run_dirs=True)
    target = out/'product/target'
    product = product_evidence(result, target/'events.jsonl')
    ready = product_ready(result)
    root, player_log = official_root(args.snapshot, target, out, mode)
    process = pv.run_command([sys.executable, str(Path(__file__).resolve()), '--official-root', str(root), '--mode', mode],
        out/'official-stdout.log', timeout=180, memory_limit=2*1024**3, watch_paths=(player_log,))
    official = read_evidence(player_log, process, worker=False)
    pv.write_json(out/'private-evidence.json', {'product': product, 'official': official})
    row = evidence.event_gate(product, official) if mode == 'event' else evidence.material_gate(official)
    row['diagnostics'] = {label: evidence.diagnostic_summary(value) for label, value in (('product', product), ('official', official))}
    if not ready:
        row['gatePassed'] = False
        row['stopReasons'] = sorted(set([*row['stopReasons'], 'product.observationIncomplete']))
    row['executionStatus'] = 'interrupted' if process['interrupted'] or product['interrupted'] else 'completed'
    return row


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--worker', type=Path, default=REPO/'worker/bin')
    p.add_argument('--harmony-dll', type=Path)
    p.add_argument('--official-root', type=Path)
    p.add_argument('--mode', choices=('material', 'event'))
    a = p.parse_args(argv)
    if a.official_root is not None:
        if a.mode is None: p.error('official mode required')
        launch_official(a.official_root, a.mode)
    if any(x is None for x in (a.out, a.snapshot, a.harmony_dll)):
        p.error('snapshot, out and harmony-dll required')
    a.out = a.out.resolve(); a.snapshot = a.snapshot.resolve(); a.harmony_dll = a.harmony_dll.resolve()
    if a.out.exists() or a.out == REPO or REPO in a.out.parents:
        p.error('out must be new and outside checkout')
    a.out.mkdir(parents=True, mode=0o700)
    summary = {'schemaVersion': 1, 'c0Passed': False, 'cases': []}
    for mode in ('material', 'event'):
        try:
            row = run_case(mode, a)
        except FixtureBuildFailure as error:
            row = {'case': mode, 'executionStatus': 'notStarted', 'gatePassed': False,
                   'c0Passed': False, 'stopReasons': ['fixtureBuildFailed'], 'buildErrors': error.diagnostics}
        except (OSError, ValueError, RuntimeError):
            row = {'case': mode, 'executionStatus': 'notStarted', 'gatePassed': False,
                   'c0Passed': False, 'stopReasons': ['privatePreparationOrExecutionFailed']}
        summary['cases'].append(row)
        pv.write_json(a.out/'safe-summary.json', summary)
    return 0 if all(r['gatePassed'] for r in summary['cases']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
