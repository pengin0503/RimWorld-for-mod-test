"""DEVELOPMENT-ONLY qualification experiment. Not part of the product.

Runs each fixture case twice on the same private snapshot:
  1. through the product Controller/Worker (tools/validation_host.py), and
  2. through the official executable in headless mode with -QuitAfterBoot,
and compares the error/warning lines and the [RWMT-PROBE] facts both boots log.
The product never imports or calls this file (tests/test_validation_host.py
checks that). It exists so the qualification evidence in
docs/research/test-host-qualification.md can be reproduced.

The official executable here runs in a throwaway copy layout with its own HOME
and XDG directories; it never touches a normal game profile.

Usage:
  python3 experiments/official-comparison/compare_official.py --snapshot S --harmony-dll H --out O [--cases ...]
  python3 experiments/official-comparison/compare_official.py --snapshot S --harmony-dll H --out O --request NAME=request.json ...
"""
from __future__ import annotations

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
sys.path.insert(0, str(REPO / 'tools'))
sys.path.insert(0, str(REPO / 'tests' / 'integration'))
import validation_host  # noqa: E402
import run_fixture_matrix as matrix  # noqa: E402

LOG_LINE = re.compile(r'^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+\s+(ERROR|WARN|INFO)\s+\[([^\]]+)\] (.*)$')
# Differences that follow from documented design choices, not from the load itself.
EXPECTED_OFFICIAL_ONLY = (
    re.compile(r'^\[Steamworks\.NET\] SteamAPI\.Init\(\) failed'),  # the Worker skips Steam on purpose
)
# Errors of the official main-menu frame loop after a failed load; the Worker has no such loop.
OFFICIAL_FRAME_LOOP = (
    re.compile(r'Root level exception in Update\(\)'),
)
CASE_NAME = re.compile(r'[A-Za-z0-9._-]+')
DLC = ('Core', 'Royalty', 'Ideology', 'Biotech', 'Odyssey')
COMPARISON_CASES = {
    'core-only': (['comparisonprobe'], ('Core',), 'English', 'A'),
    'ok': (['*okxml', 'comparisonprobe'], ('Core',), 'English', 'A'),
    'ok-all-dlc-japanese': (['*okxml', 'comparisonprobe'], DLC, 'Japanese', 'A'),
    'side-effect': (['*sideeffect', 'comparisonprobe'], ('Core',), 'English', 'A'),
    'bad-patch': (['*badpatch', 'comparisonprobe'], ('Core',), 'English', 'A'),
    'bad-reference': (['*badref', 'comparisonprobe'], ('Core',), 'English', 'A'),
    'init-exception': (['*initthrow', 'comparisonprobe'], ('Core',), 'English', 'A'),
    'harmony-ok': (['harmonylib', '*harmonyok', 'comparisonprobe'], ('Core',), 'English', 'AB'),
    'harmony-missing': (['harmonylib', '*harmonymissing', 'comparisonprobe'], ('Core',), 'English', 'AB'),
}
# Map stage vs the official developer quick test (-quicktest). The mapprobe fixture makes the
# official quick test use the product's default seed and logs a map fingerprint in both runs.
MAP_COMPARISON_CASES = {
    'map-core': (['harmonylib', 'mapprobe', '*okxml', 'comparisonprobe'], ('Core',), 'English'),
    'map-structure': (['harmonylib', 'mapprobe', '*mapstructure', 'comparisonprobe'], ('Core',), 'English'),
    'map-genstep-throws': (['harmonylib', 'mapprobe', '*mapgenthrow', 'comparisonprobe'], ('Core',), 'English'),
    'map-all-dlc': (['harmonylib', 'mapprobe', '*mapstructure', 'comparisonprobe'], DLC, 'English'),
}


def worker_lines(events):
    errors, probes = [], []
    for event in events:
        first = (event.get('message') or '').splitlines()[0] if event.get('message') else ''
        if event.get('level') in ('error', 'warning'):
            errors.append(f'{event["level"]} [{event["category"]}] {first}')
        elif first.startswith('[RWMT-PROBE]'):
            probes.append(first)
    return errors, probes


def official_lines(player_log):
    errors, probes = [], []
    for line in player_log.read_text(encoding='utf-8', errors='replace').splitlines():
        match = LOG_LINE.match(line)
        if not match:
            continue
        level, category, message = match.groups()
        if message.startswith('[RWMT-PROBE]'):
            probes.append(message)
        elif level in ('ERROR', 'WARN'):
            if not any(p.search(message) for p in EXPECTED_OFFICIAL_ONLY):
                errors.append(f'{"error" if level == "ERROR" else "warning"} [{category}] {message}')
    return errors, probes


def run_official(snapshot, target_run, mods, official, out, timeout=180, extra_args=()):
    game = Path(snapshot) / 'game'
    root = out / 'official'
    root.mkdir(parents=True)
    for name in os.listdir(game):
        if name not in ('RimWorld', 'Data'):
            os.symlink(game / name, root / name)
    shutil.copyfile(game / 'RimWorld', root / 'RimWorld')
    (root / 'RimWorld').chmod(0o755)
    (root / 'Data').mkdir()
    for folder in official:
        os.symlink(game / 'Data' / folder, root / 'Data' / folder)
    (root / 'Mods').mkdir()
    for mod in mods:
        shutil.copytree(mod['sourcePath'], root / 'Mods' / mod['folderName'])
    config = root / 'xdg' / 'unity3d' / 'Ludeon Studios' / 'RimWorld by Ludeon Studios' / 'Config'
    config.mkdir(parents=True)
    for name in ('ModsConfig.xml', 'Prefs.xml'):
        shutil.copyfile(Path(target_run) / 'userdata' / 'Config' / name, config / name)
    (root / 'home').mkdir()
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(root / 'home'), 'XDG_CONFIG_HOME': str(root / 'xdg'),
           'LANG': 'C.UTF-8'}
    started = time.monotonic()
    with open(root / 'stdout.log', 'wb') as stdout:
        try:
            code = subprocess.run(['./RimWorld', '-headless', '-QuitAfterBoot', '-NoCrashDialog', *extra_args], cwd=root, env=env,
                                  stdin=subprocess.DEVNULL, stdout=stdout, stderr=subprocess.STDOUT, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            # When loading fails, the official boot never reaches QuitAfterBoot and keeps
            # running its frame loop; subprocess.run has killed it at this point.
            code = 'timeout'
    seconds = time.monotonic() - started
    player_log = config.parent / 'Logs' / 'Player.log'
    return code, round(seconds, 3), player_log


def official_errors_until_map(player_log):
    errors = []
    for line in player_log.read_text(encoding='utf-8', errors='replace').splitlines():
        match = LOG_LINE.match(line)
        if not match:
            continue
        level, category, message = match.groups()
        if message.startswith('[RWMT-PROBE] map pawns'):
            break
        if level in ('ERROR', 'WARN') and not any(p.search(message) for p in EXPECTED_OFFICIAL_ONLY):
            errors.append(f'{"error" if level == "ERROR" else "warning"} [{category}] {message}')
    return errors


def compare_case(name, request, official, case_dir, args, *, quicktest=False):
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)
    (case_dir / 'request.json').write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding='utf-8')
    # keep_run_dirs: the official run below copies the mods from the Controller's sourcePath,
    # which for ZIP inputs is the extraction under product/inputs.
    result = validation_host.run_validation(args.snapshot, case_dir / 'request.json', case_dir / 'product', args.worker,
                                            keep_run_dirs=True)
    if result['status'] == 'blocked':
        print(f'{name:24} product blocked: {result["reasons"]}', flush=True)
        return {'case': name, 'productStatus': 'blocked', 'errorsMatch': False, 'probesMatch': False}
    target_run = case_dir / 'product' / 'target'
    events = [json.loads(line) for line in (target_run / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
    w_errors, w_probes = worker_lines(events)
    code, seconds, player_log = run_official(args.snapshot, target_run, result['mods'], official, case_dir, args.official_timeout,
                                             ('-quicktest',) if quicktest else ())
    o_errors, o_probes = official_lines(player_log) if player_log.is_file() else ([], [])
    if quicktest:
        # The official quick test goes on after the map: game start and 180 played frames before
        # QuitAfterBoot. Only what both runs can see is compared: the map fingerprint and the
        # errors up to the end of map generation (the probe's last map line in the official log).
        o_errors = official_errors_until_map(player_log) if player_log.is_file() else []
    if code == 'timeout':
        # The frame loop repeats its errors every frame until the kill, so only the
        # distinct lines are comparable, and the loop's own errors are left out.
        o_errors = sorted({e for e in o_errors if not any(p.search(e) for p in OFFICIAL_FRAME_LOOP)})
        w_errors = sorted(set(w_errors))
    row = {
        'case': name, 'productStatus': result['status'], 'productReasons': [r['code'] for r in result['reasons']],
        'officialExitCode': code, 'officialSeconds': seconds, 'productTargetSeconds': result['timings'].get('targetSeconds'),
        'errorsMatch': sorted(w_errors) == sorted(o_errors), 'probesMatch': sorted(w_probes) == sorted(o_probes),
        'workerOnlyErrors': sorted(set(w_errors) - set(o_errors)), 'officialOnlyErrors': sorted(set(o_errors) - set(w_errors)),
        'errorCounts': {'worker': len(w_errors), 'official': len(o_errors)}, 'distinctOnly': code == 'timeout',
        'workerOnlyProbes': sorted(set(w_probes) - set(o_probes)), 'officialOnlyProbes': sorted(set(o_probes) - set(w_probes)),
        'probes': sorted(w_probes),
    }
    print(f'{name:24} product={result["status"]:10} errorsMatch={row["errorsMatch"]} probesMatch={row["probesMatch"]} '
          f'official={seconds:.1f}s product-target={row["productTargetSeconds"]}s', flush=True)
    for key in ('workerOnlyErrors', 'officialOnlyErrors', 'workerOnlyProbes', 'officialOnlyProbes'):
        for line in row[key]:
            print(f'    {key}: {line[:200]}')
    return row


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--harmony-dll', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--worker', default=str(REPO / 'worker' / 'bin'))
    parser.add_argument('--cases')
    parser.add_argument('--map', action='store_true',
                        help='compare the map stage with the official -quicktest map (MAP_COMPARISON_CASES)')
    parser.add_argument('--official-timeout', type=int, default=180)
    parser.add_argument('--request', action='append', metavar='NAME=PATH',
                        help='compare a private request file (e.g. real mods) instead of the fixture cases')
    args = parser.parse_args(argv)
    for item in args.request or []:
        # The name becomes a directory under out/cases that is deleted and recreated.
        name, _, path = item.partition('=')
        if not CASE_NAME.fullmatch(name) or name in ('.', '..') or not path:
            parser.error(f'--request needs NAME=PATH with NAME made of letters, digits, ".", "_" or "-": {item!r}')
    out = Path(args.out).resolve()
    if REPO in out.parents:
        parser.error('--out must be outside the repository')
    out.mkdir(parents=True, exist_ok=True)
    matrix.ASSEMBLIES['comparisonprobe'] = 'ComparisonProbe'
    staged = matrix.build_fixtures(out, args.snapshot, Path(args.harmony_dll).resolve())
    rows = []
    jobs = []
    if args.request:
        # Private real-mod requests: compared as given, with the probe appended as a non-target mod.
        for item in args.request:
            name, _, path = item.partition('=')
            request = json.loads(Path(path).read_text(encoding='utf-8'))
            base = Path(path).resolve().parent
            for mod in request['mods']:
                mod['path'] = str((base / mod['path']).resolve())
            request['mods'].append({'path': str(staged / 'comparisonprobe')})
            jobs.append((name, request, tuple(request.get('official', ['Core']))))
    elif args.map:
        for name in (args.cases.split(',') if args.cases else MAP_COMPARISON_CASES):
            mod_names, official, language = MAP_COMPARISON_CASES[name]
            request = matrix.case('A', mod_names, official=official, language=language, map={},
                                  limits={'timeoutSeconds': 600})
            for mod in request['mods']:
                mod['path'] = str(staged / mod['path'])
            jobs.append((name, request, official))
    else:
        for name in (args.cases.split(',') if args.cases else COMPARISON_CASES):
            mod_names, official, language, levels = COMPARISON_CASES[name]
            request = matrix.case(levels, mod_names, official=official, language=language)
            if not any(m['target'] for m in request['mods']):
                request['mods'][-1]['target'] = True
            for mod in request['mods']:
                mod['path'] = str(staged / mod['path'])
            if 'B' in levels:
                request['expectations'] = {'harmonyPatches': [matrix.HARMONY_OK]}
            jobs.append((name, request, official))
    for name, request, official in jobs:
        rows.append(compare_case(name, request, official, out / 'cases' / name, args, quicktest=args.map))
    (out / 'comparison.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'comparison: {out / "comparison.json"}')
    return 0 if all(r['errorsMatch'] and r['probesMatch'] for r in rows) else 1


if __name__ == '__main__':
    sys.exit(main())
