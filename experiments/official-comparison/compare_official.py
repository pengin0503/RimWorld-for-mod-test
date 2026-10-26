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
import statistics
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
        if validation_host.known_noise(event):
            continue  # the same engine noise the product leaves out of its verdict
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


def compare_case(name, request, official, case_dir, args):
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
    code, seconds, player_log = run_official(args.snapshot, target_run, result['mods'], official, case_dir, args.official_timeout)
    o_errors, o_probes = official_lines(player_log) if player_log.is_file() else ([], [])
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


# Probe lines that identify the map setup; equal in every run of a case.
MAP_IDENTITY = re.compile(r'^\[RWMT-PROBE\] (map world |mods )')
# Probe lines with counts; compared as distributions because generation is not reproducible.
MAP_METRIC = re.compile(r'^\[RWMT-PROBE\] map (things count|category [^=\s]+|thing-count [^=\s]+|terrain-cells [^=\s]+|roofed-cells)=(\d+)')


def map_metrics(probes):
    metrics = {}
    for line in probes:
        match = MAP_METRIC.match(line)
        if match:
            metrics[match.group(1)] = int(match.group(2))
    return metrics


def compare_distributions(product_runs, official_runs):
    """Per metric: is the product's median inside the official runs' range, widened by a tolerance?

    The median keeps one rare outcome (a ruin that happens to pick the same floor as a fixed
    structure) from moving the comparison. The tolerance is the official range itself (at least
    2 % of the official mean and at least 2), so a metric that does not vary in the official runs
    must match within that small margin.
    A metric missing from a run counts as 0. Metrics present in some but not all runs of a side
    (intermittent kinds, e.g. which stone a ruin's floor happens to use) are not judged one by
    one: a handful of runs cannot tell a rare kind from a missing one. Their per-run sum per
    metric group is judged instead, so a side that drops or adds such content still shows.
    A kind present in every run of one side and in none of the other is always judged.
    """
    names = sorted({k for run in product_runs + official_runs for k in run})
    values = {name: ([run.get(name, 0) for run in product_runs], [run.get(name, 0) for run in official_runs])
              for name in names}
    def partial(side):
        return 0 in side and any(side)

    intermittent = [name for name, (p, o) in values.items() if partial(p) or partial(o)]
    for group in sorted({name.split(' ', 1)[0] for name in intermittent}):
        members = [name for name in intermittent if name.split(' ', 1)[0] == group]
        values[f'{group} (sum of intermittent kinds)'] = tuple(
            [sum(values[name][side][i] for name in members) for i in range(len(values[members[0]][side]))] for side in (0, 1))
    rows, outside = {}, []
    for name, (p, o) in values.items():
        o_mean, p_median = sum(o) / len(o), statistics.median(p)
        tolerance = max(max(o) - min(o), 0.02 * o_mean, 2)
        judged = name not in intermittent
        ok = min(o) - tolerance <= p_median <= max(o) + tolerance
        rows[name] = {'product': p, 'official': o, 'productMedian': p_median, 'officialMedian': statistics.median(o),
                      'tolerance': round(tolerance, 1), 'judged': judged, 'withinTolerance': ok}
        if judged and not ok:
            outside.append(name)
    return rows, outside


def compare_map_case(name, request, official, case_dir, args):
    """Map stage vs official -quicktest, repeated: generation differs from run to run on this build
    (the official quick test too), so single fingerprints cannot match. Compared instead:
    the setup lines (identical), the errors up to the end of map generation (identical in every run),
    and the count metrics as distributions (compare_distributions)."""
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)
    (case_dir / 'request.json').write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding='utf-8')
    statuses = []
    for i in range(args.repeat):
        run_dir = case_dir / f'run{i + 1}'
        result = validation_host.run_validation(args.snapshot, case_dir / 'request.json', run_dir / 'product', args.worker,
                                                keep_run_dirs=True, baseline_cache=case_dir / 'baseline-cache')
        statuses.append(result['status'])
        if result['status'] == 'blocked':
            print(f'{name:24} product blocked: {result["reasons"]}', flush=True)
            return {'case': name, 'productStatus': 'blocked', 'equivalent': False}
        code, seconds, _ = run_official(args.snapshot, run_dir / 'product' / 'target', result['mods'], official, run_dir,
                                        args.official_timeout, ('-quicktest',))
        (run_dir / 'official-run.json').write_text(json.dumps({'exitCode': code, 'seconds': seconds}), encoding='utf-8')
    return analyze_map_case(name, case_dir)


def load_map_runs(case_dir):
    """The product and official observations of every run kept under case_dir/run<N>."""
    runs = {'product': [], 'official': []}
    statuses = []
    for run_dir in sorted(case_dir.glob('run*'), key=lambda p: int(p.name[3:])):
        result = json.loads((run_dir / 'product' / 'result.json').read_text(encoding='utf-8'))
        statuses.append(result['status'])
        events = [json.loads(line) for line in
                  (run_dir / 'product' / 'target' / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
        w_errors, w_probes = worker_lines(events)
        runs['product'].append({'errors': sorted(w_errors), 'probes': w_probes})
        player_log = run_dir / 'official' / 'xdg' / 'unity3d' / 'Ludeon Studios' / 'RimWorld by Ludeon Studios' / 'Logs' / 'Player.log'
        _, o_probes = official_lines(player_log) if player_log.is_file() else ([], [])
        o_errors = official_errors_until_map(player_log) if player_log.is_file() else []
        runs['official'].append({'errors': sorted(o_errors), 'probes': o_probes})
    return runs, statuses


def map_generated(probes):
    """Whether the probe logged a generated map (its world line and its thing count) in this run."""
    return any(p.startswith('[RWMT-PROBE] map world ') for p in probes) and 'things count' in map_metrics(probes)


def analyze_map_case(name, case_dir):
    runs, statuses = load_map_runs(case_dir)
    return summarize_map_runs(name, runs, statuses)


def summarize_map_runs(name, runs, statuses):
    identity = {side: sorted({tuple(sorted(p for p in r['probes'] if MAP_IDENTITY.match(p))) for r in rs})
                for side, rs in runs.items()}
    errors = {side: sorted({tuple(r['errors']) for r in rs}) for side, rs in runs.items()}
    metrics, outside = compare_distributions([map_metrics(r['probes']) for r in runs['product']],
                                             [map_metrics(r['probes']) for r in runs['official']])
    fingerprints = {side: len({tuple(p for p in r['probes'] if ' sha=' in p) for r in rs}) for side, rs in runs.items()}
    repeat = len(statuses)
    row = {
        'case': name, 'repeat': repeat, 'productStatuses': statuses,
        # Two sides that both stopped before the map would otherwise agree on everything.
        'mapGeneratedInAllRuns': {side: bool(rs) and all(map_generated(r['probes']) for r in rs) for side, rs in runs.items()},
        'identityMatch': len(identity['product']) == 1 and identity['product'] == identity['official'],
        'identity': [list(x) for x in identity['product']],
        'errorsMatch': len(errors['product']) == 1 and errors['product'] == errors['official'],
        'errors': {side: [list(x) for x in v] for side, v in errors.items()},
        'distinctFingerprints': fingerprints,
        'metricsOutsideTolerance': outside, 'metrics': metrics,
    }
    row['equivalent'] = all(row['mapGeneratedInAllRuns'].values()) and row['identityMatch'] and row['errorsMatch'] \
        and not outside
    print(f'{name:24} equivalent={row["equivalent"]} generated={row["mapGeneratedInAllRuns"]} identity={row["identityMatch"]} errors={row["errorsMatch"]} '
          f'outside={outside} distinct fingerprints product/official={fingerprints["product"]}/{fingerprints["official"]} '
          f'of {repeat}', flush=True)
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
    parser.add_argument('--repeat', type=int, default=5, help='with --map: runs per side for the distribution comparison')
    parser.add_argument('--reanalyze', action='store_true',
                        help='with --map: recompute comparison.json from the runs already kept under --out')
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
    if args.reanalyze:
        if not args.map:
            parser.error('--reanalyze needs --map')
        names = args.cases.split(',') if args.cases else [d.name for d in sorted((out / 'cases').iterdir())]
        rows = [analyze_map_case(name, out / 'cases' / name) for name in names]
        (out / 'comparison.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'comparison: {out / "comparison.json"}')
        return 0 if all(r['equivalent'] for r in rows) else 1
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
        if args.map:
            rows.append(compare_map_case(name, request, official, out / 'cases' / name, args))
        else:
            rows.append(compare_case(name, request, official, out / 'cases' / name, args))
    (out / 'comparison.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'comparison: {out / "comparison.json"}')
    if args.map:
        return 0 if all(r['equivalent'] for r in rows) else 1
    return 0 if all(r['errorsMatch'] and r['probesMatch'] for r in rows) else 1


if __name__ == '__main__':
    sys.exit(main())
