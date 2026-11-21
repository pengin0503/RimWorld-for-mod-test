"""DEVELOPMENT-ONLY automatic qualification of a new RimWorld 1.7 build. Not part of the product.

When the game is updated (a new ``1.7.<build> rev<revision>`` in Version.txt), the host
runs that build at once, but as ``experimental``. This script repeats, unattended, the
comparisons that qualified 1.7.4985 (docs/research/test-host-qualification.md,
docs/research/map-qualification.md) on the new build and writes a qualification record
for exactly its files when they all agree:

1. the private fixture matrix (tests/integration/run_fixture_matrix.py): every case must
   end with its expected status and reasons;
2. A/B against the official executable's ``-headless -QuitAfterBoot`` boot
   (compare_official.py): errors/warnings and probe facts must be identical in all cases
   -> levels A and B;
3. the map stage against the official ``-quicktest`` map, as distributions over repeated
   runs judged by one permutation test over all metrics (compare_official.py --map) -> feature ``map``;
4. the bounded tick (D) real-game acceptance (tests/integration/run_bounded_tick.py, the basis D
   had on 1.7.4985) and the D v2 smoke (tests/integration/run_bounded_tick_v2.py), run with a
   candidate record -> experimental features ``bounded-tick.v1`` / ``bounded-tick.v2`` (D stays
   experimental). The independent comparison with the official tick loop (compare_ticks.py) runs
   too, but only as information: it has not agreed on any build yet.

A stage that does not agree grants nothing; nothing is ever granted from a version number.
The record goes to the private qualification store (``--store``, read by the Controller
through ``--qualification-store`` or ``$RWMT_QUALIFICATION_STORE``) and is tied to the
Worker build that was compared. A copy without the Worker hash is written next to the
evidence as ``committed-qualification.json``; adding it to
``validation-data/<build id>/qualification.json`` in a reviewed pull request makes the
qualification apply to every later session.

Everything this script writes stays under --out and --store, which must be outside the
repository. The official executable runs only inside compare_official.py/compare_ticks.py,
in throwaway layouts with their own HOME/XDG directories.

Usage:
  python3 experiments/official-comparison/qualify_build.py --snapshot S --harmony-dll H --out O --store Q
      [--worker W] [--map-repeat 10] [--skip-map] [--skip-ticks] [--force]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools'))
import game_builds  # noqa: E402
import validation_host  # noqa: E402

HERE = Path(__file__).resolve().parent
TOOL = 'qualify_build.py/1'
PLATFORM = 'linux-x64'
RUNTIME = 'waylith'


def _outside_repo(path):
    path = Path(path).expanduser().resolve()
    if path == REPO or REPO in path.parents:
        raise SystemExit(f'{path} must be outside the repository')
    return path


def _run(cmd, log, env_store):
    """Run one stage as its own process; its output goes to a private log under --out."""
    env = dict(os.environ)
    env[game_builds.STORE_ENV] = str(env_store) if env_store else ''
    started = time.monotonic()
    with open(log, 'wb') as stream:
        code = subprocess.run([sys.executable, *map(str, cmd)], cwd=REPO, env=env, stdin=subprocess.DEVNULL,
                              stdout=stream, stderr=subprocess.STDOUT).returncode
    return code, round(time.monotonic() - started, 1)


def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def matrix_stage(args, out):
    code, seconds = _run([REPO / 'tests' / 'integration' / 'run_fixture_matrix.py', '--snapshot', args.snapshot,
                          '--harmony-dll', args.harmony_dll, '--out', out / 'matrix', '--worker', args.worker],
                         out / 'matrix.log', None)
    rows = _read(out / 'matrix' / 'matrix.json') or []
    bad = sorted(r['case'] for r in rows if not r.get('ok'))
    ok = code == 0 and bool(rows) and not bad
    return ok, {'cases': len(rows), 'asExpected': len(rows) - len(bad), 'notAsExpected': bad, 'seconds': seconds}


def official_ab_stage(args, out):
    code, seconds = _run([HERE / 'compare_official.py', '--snapshot', args.snapshot, '--harmony-dll', args.harmony_dll,
                          '--out', out / 'official-ab', '--worker', args.worker], out / 'official-ab.log', None)
    rows = _read(out / 'official-ab' / 'comparison.json') or []
    bad = sorted(r['case'] for r in rows if not (r.get('errorsMatch') and r.get('probesMatch')))
    ok = code == 0 and bool(rows) and not bad
    return ok, {'cases': len(rows), 'matched': len(rows) - len(bad), 'notMatched': bad, 'seconds': seconds}


def map_stage(args, out):
    code, seconds = _run([HERE / 'compare_official.py', '--snapshot', args.snapshot, '--harmony-dll', args.harmony_dll,
                          '--out', out / 'official-map', '--worker', args.worker, '--map', '--repeat', args.map_repeat],
                         out / 'official-map.log', None)
    rows = _read(out / 'official-map' / 'comparison.json') or []
    bad = sorted(r['case'] for r in rows if not r.get('equivalent'))
    ok = code == 0 and bool(rows) and not bad
    return ok, {'cases': len(rows), 'repeat': args.map_repeat, 'equivalent': len(rows) - len(bad),
                'notEquivalent': bad, 'seconds': seconds}


D_V1_CASES = 10  # tests/integration/run_bounded_tick.py


def tick_stages(args, out, candidate_store):
    """D's real-game acceptance on this build; the official tick comparison is information only.

    D is experimental on every build. On 1.7.4985 it was enabled from the real-game acceptance
    (docs/research/2026-10-29-bounded-tick.md) and the v2 smoke, not from the official tick
    comparison, which has never agreed on any build: the fixed view follows the generated start
    spot, which differs between runs (docs/research/2026-10-29-bounded-tick-independent-comparison.md).
    """
    code, seconds = _run([REPO / 'tests' / 'integration' / 'run_bounded_tick.py', '--snapshot', args.snapshot,
                          '--worker', args.worker, '--out', out / 'ticks-v1'], out / 'ticks-v1.log', candidate_store)
    runs = (_read(out / 'ticks-v1' / 'safe-summary.json') or {}).get('runs', [])
    passed = sum(1 for r in runs if r.get('ok') is True)
    v1 = code == 0 and len(runs) == D_V1_CASES and passed == D_V1_CASES
    rows = {'boundedTickV1': {'ok': v1, 'cases': len(runs), 'asExpected': passed, 'seconds': seconds}}
    if v1:
        code, seconds = _run([REPO / 'tests' / 'integration' / 'run_bounded_tick_v2.py', '--snapshot', args.snapshot,
                              '--worker', args.worker, '--out', out / 'ticks-v2'], out / 'ticks-v2.log', candidate_store)
        safe = _read(out / 'ticks-v2' / 'safe-summary.json') or {}
        rows['boundedTickV2'] = {'ok': code == 0 and safe.get('ok') is True, 'cases': safe.get('totalCases'),
                                 'asExpected': safe.get('passedCases'), 'seconds': seconds}
    code, seconds = _run([HERE / 'compare_ticks.py', '--snapshot', args.snapshot, '--harmony-dll', args.harmony_dll,
                          '--out', out / 'ticks-official', '--worker', args.worker], out / 'ticks-official.log',
                         candidate_store)
    summary = _read(out / 'ticks-official' / 'safe-summary.json') or {}
    # Fixed fault labels only (compare_ticks.compare); grants nothing either way.
    rows['officialTickComparison'] = {
        'informationOnly': True, 'agrees': code == 0 and summary.get('ok') is True,
        'runs': len(summary.get('runs', [])),
        'faults': sorted({f for r in summary.get('runs', []) for f in r.get('faults', []) if isinstance(f, str)}),
        'seconds': seconds}
    return v1, v1 and rows['boundedTickV2']['ok'], rows


def build_record(snapshot, *, levels, features, experimental, worker_sha, comparison):
    files = snapshot['files']
    record = {
        'recordType': game_builds.RECORD_TYPE, 'schemaVersion': game_builds.SCHEMA_VERSION,
        'gameVersion': snapshot['version'], 'buildId': game_builds.build_id(snapshot['version']),
        'method': 'automatic', 'createdAt': validation_host._now(),
        'identitySha256': {name: files[name]['sha256'] for name in game_builds.IDENTITY_FILES},
        'experimentalFeatures': list(experimental),
        'qualified': [],
        'comparison': comparison,
    }
    if levels:
        entry = {'platform': PLATFORM, 'runtime': RUNTIME, 'levels': list(levels), 'features': list(features),
                 'runtimeSha256': {name: files[name]['sha256'] for name in game_builds.RUNTIME_FILES[PLATFORM]},
                 'evidence': 'automatic: experiments/official-comparison/qualify_build.py (summary in comparison)'}
        if features:
            entry['featureEvidence'] = {name: 'automatic: compare_official.py --map (summary in comparison.map)'
                                        for name in features}
        record['qualified'].append(entry)
    if worker_sha:
        record['worker'] = {'sha256': worker_sha}
    return game_builds.validate_record(record)


def _git(*args):
    try:
        return subprocess.run(['git', *args], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _source_state():
    """The checkout the comparison ran from: HEAD and whether tracked/untracked files differ from it."""
    status = _git('status', '--porcelain', '--untracked-files=normal')
    return {'repositoryCommit': _git('rev-parse', 'HEAD'), 'repositoryClean': None if status is None else status == ''}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--harmony-dll', required=True)
    parser.add_argument('--out', required=True, help='new private directory for the comparison evidence')
    parser.add_argument('--store', required=True, help='private qualification store the record is written to')
    parser.add_argument('--worker', default=str(REPO / 'worker' / 'bin'))
    # 10 runs per side: the permutation test of the map stage then detects a shift of 3 sd in one
    # metric most of the time (docs/research/2026-11-21-build-1.7.5014.md).
    parser.add_argument('--map-repeat', type=int, default=10)
    parser.add_argument('--skip-map', action='store_true', help='do not qualify the map stage')
    parser.add_argument('--skip-ticks', action='store_true', help='do not enable the experimental D cases')
    parser.add_argument('--force', action='store_true', help='qualify even if a reviewed record already applies')
    args = parser.parse_args(argv)
    out, store = _outside_repo(args.out), _outside_repo(args.store)
    args.snapshot, args.harmony_dll = Path(args.snapshot).resolve(), Path(args.harmony_dll).resolve()
    args.worker = Path(args.worker).resolve()
    if out.exists() and any(out.iterdir()):
        parser.error(f'{out} is not empty')
    if not 4 <= args.map_repeat <= 20:
        # Fewer than 4 runs per side cannot show any difference at the 5 % level.
        parser.error('--map-repeat must be 4..20')
    snapshot = validation_host.load_snapshot(args.snapshot, full=True)
    version = snapshot['version']
    if game_builds.family(version) is None:
        print(json.dumps({'status': 'unsupported', 'version': version,
                          'detail': validation_host.unsupported_build_detail(version)}, ensure_ascii=False))
        return 2
    if snapshot.get('buildPlatform') != PLATFORM:
        parser.error('automatic qualification compares the Linux build only')
    name, adapter = validation_host.match_adapter(snapshot['files'])
    if adapter is not None and not args.force:
        print(json.dumps({'status': 'alreadyQualified', 'version': version, 'adapter': name,
                          'record': adapter.get('record')}, ensure_ascii=False))
        return 0
    worker_sha = validation_host.sha256_file(args.worker / f'{validation_host.WORKER_NAME}.dll')
    out.mkdir(parents=True, exist_ok=True)
    store.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    comparison = {'tool': TOOL, **_source_state(), 'platform': PLATFORM, 'runtime': RUNTIME}
    levels, features, experimental = (), (), ()

    def progress(stage, ok, row):
        comparison[stage] = row
        print(f'{stage:16} {"agrees" if ok else "DIFFERS"} {json.dumps(row, ensure_ascii=False)}', flush=True)

    matrix_ok, row = matrix_stage(args, out)
    progress('matrix', matrix_ok, row)
    ab_ok, row = official_ab_stage(args, out)
    progress('officialAB', ab_ok, row)
    if matrix_ok and ab_ok:
        levels = ('A', 'B')
        if not args.skip_map:
            map_ok, row = map_stage(args, out)
            progress('map', map_ok, row)
            features = ('map',) if map_ok else ()
        if not args.skip_ticks:
            candidate = out / 'candidate-store'
            candidate.mkdir(exist_ok=True)
            trial = build_record(snapshot, levels=levels, features=features, experimental=game_builds.EXPERIMENTAL_FEATURES,
                                 worker_sha=worker_sha, comparison={'tool': TOOL, 'candidate': True})
            (candidate / game_builds.record_file_name(trial, snapshot['fingerprint'])).write_text(
                json.dumps(trial, indent=2), encoding='utf-8')
            v1, v2, rows = tick_stages(args, out, candidate)
            for stage, stage_row in rows.items():
                progress(stage, stage_row.get('ok', stage_row.get('agrees')), stage_row)
            experimental = tuple(f for f, ok in (('bounded-tick.v1', v1), ('bounded-tick.v2', v2)) if ok)
    comparison['seconds'] = round(time.monotonic() - started, 1)
    record = build_record(snapshot, levels=levels, features=features, experimental=experimental,
                          worker_sha=worker_sha, comparison=comparison)
    committed = {k: v for k, v in record.items() if k != 'worker'}
    if not levels:
        (out / 'qualification-failed.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'status': 'notQualified', 'version': version, 'evidence': str(out)}, ensure_ascii=False))
        return 1
    path = store / game_builds.record_file_name(record, snapshot['fingerprint'])
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (out / 'committed-qualification.json').write_text(json.dumps(committed, ensure_ascii=False, indent=2) + '\n',
                                                      encoding='utf-8')
    print(json.dumps({'status': 'qualified', 'version': version, 'levels': list(levels), 'features': list(features),
                      'experimentalFeatures': list(experimental), 'record': str(path),
                      'committedCopy': str(out / 'committed-qualification.json')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
