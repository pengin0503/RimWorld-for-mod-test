"""DEVELOPMENT-ONLY timing experiment for docs/research/test-host-performance.md.

Measures, on one machine and one snapshot, with the OS file cache warm (it cannot
be dropped in the cloud container, so nothing here is a cold-start number):
  prepare   tools/validation_host.py prepare-game (copy + SHA-256 + read-only)
  run       a full Controller run without baseline cache (baseline + target)
  cached    the same run with the baseline taken from the cache
  official  the official executable, headless with -QuitAfterBoot, same mods/prefs
            (dev-only reference; the product never starts it)

Usage:
  python3 experiments/performance/measure.py --source GAME --snapshot-root DIR --fixtures STAGED --out O [--repeat 5]
STAGED is the fixtures directory staged by tests/integration/run_fixture_matrix.py.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import statistics
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools'))
sys.path.insert(0, str(REPO / 'experiments' / 'official-comparison'))
import validation_host  # noqa: E402
import compare_official  # noqa: E402

SCENARIOS = {
    'core+okxml/English': (('Core',), 'English'),
    'all-dlc+okxml/Japanese': (('Core', 'Royalty', 'Ideology', 'Biotech', 'Odyssey'), 'Japanese'),
}


def summary(values):
    return {'n': len(values), 'median': round(statistics.median(values), 2), 'min': round(min(values), 2),
            'max': round(max(values), 2), 'values': [round(v, 2) for v in values]}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--snapshot-root', required=True)
    parser.add_argument('--fixtures', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--worker', default=str(REPO / 'worker' / 'bin'))
    parser.add_argument('--repeat', type=int, default=5)
    args = parser.parse_args(argv)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report = {'prepare': [], 'scenarios': {}}

    snapshot = None
    for index in range(args.repeat):
        target = Path(args.snapshot_root) / f'snapshot-{index}'
        if target.exists():
            shutil.rmtree(target)
        started = time.monotonic()
        validation_host.prepare_game(args.source, target, log=lambda *_: None)
        report['prepare'].append(time.monotonic() - started)
        if snapshot is None:
            snapshot = target
        else:
            for path in [target, *target.rglob('*')]:
                if path.is_dir() and not path.is_symlink():
                    path.chmod(0o755)
            shutil.rmtree(target)
    report['prepare'] = summary(report['prepare'])
    print('prepare', report['prepare'], flush=True)

    for name, (official, language) in SCENARIOS.items():
        rows = {'run': [], 'cached': [], 'workerTarget': [], 'official': []}
        request = {'recordType': 'modValidationRequest', 'schemaVersion': 1, 'levels': ['A'], 'official': list(official),
                   'language': language, 'mods': [{'path': str(Path(args.fixtures) / 'okxml'), 'target': True}]}
        case = out / name.replace('/', '_')
        if case.exists():
            shutil.rmtree(case)
        case.mkdir()
        (case / 'request.json').write_text(json.dumps(request), encoding='utf-8')
        cache = case / 'cache'
        last = None
        for index in range(args.repeat):
            for kind in ('run', 'cached'):
                started = time.monotonic()
                result = validation_host.run_validation(snapshot, case / 'request.json', case / f'{kind}-{index}', args.worker,
                                                        baseline_cache=cache if kind == 'cached' else None)
                rows[kind].append(time.monotonic() - started)
                if result['status'] != 'passed' or (kind == 'cached' and not result['diagnostics']['baselineCached']
                                                    and index > 0):
                    raise SystemExit(f'{name} {kind}: unexpected result {result["status"]} {result["reasons"]}')
                rows['workerTarget'].append(result['process']['target']['seconds'])
                last = result
            code, seconds, _ = compare_official.run_official(snapshot, case / f'run-{index}' / 'target', last['mods'],
                                                             official, case / f'official-{index}')
            if code != 0:
                raise SystemExit(f'official run failed with {code}')
            rows['official'].append(seconds)
            shutil.rmtree(case / f'official-{index}')
        # The first cached run fills the cache, so only later ones are cache hits.
        rows['cachedHits'] = rows['cached'][1:]
        report['scenarios'][name] = {k: summary(v) for k, v in rows.items() if v}
        print(name, json.dumps(report['scenarios'][name]), flush=True)
    (out / 'performance.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'performance: {out / "performance.json"}')


if __name__ == '__main__':
    main()
