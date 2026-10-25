"""Private integration matrix: runs the self-made fixtures against a real game snapshot.

Needs files that are never committed: a snapshot made by
``tools/validation_host.py prepare-game`` and Lib.Harmony's 0Harmony.dll
(NuGet Lib.Harmony, net10.0). Build outputs, run directories and results go to
--out, which must be outside the repository. Public CI does not run this.

Usage:
  python3 tests/integration/run_fixture_matrix.py --snapshot S --harmony-dll H --out O [--cases ok,badref] [--runtime standard]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools'))
import validation_host  # noqa: E402

FIXTURES = REPO / 'tests' / 'fixtures' / 'validation-mods'
SOURCES = REPO / 'tests' / 'fixtures' / 'validation-mods-src'
ASSEMBLIES = {'initthrow': 'InitThrow', 'harmonyok': 'HarmonyOk', 'harmonymissing': 'HarmonyMissing'}

OK_EXPECTATIONS = {
    'defs': [{'type': 'ThingDef', 'defName': 'RWMT_Widget', 'exists': True}],
    'defValues': [
        {'type': 'ThingDef', 'defName': 'Steel', 'path': 'deepCountPerPortion', 'equals': '60'},
        {'type': 'ThingDef', 'defName': 'RWMT_Widget', 'path': 'thingCategories[0]', 'equals': 'ResourcesRaw'},
        {'type': 'ThingDef', 'defName': 'RWMT_Widget', 'path': 'statBases[stat=Mass].value', 'equals': '0.5'},
    ],
    'keyed': [{'key': 'RWMT_Hello', 'equals': 'Hello from the validation fixture'}],
}


def patch(owner, patch_type):
    return {'owner': owner, 'targetAssembly': 'Assembly-CSharp', 'targetType': 'Verse.GenText',
            'targetMethod': 'ToSpaceList', 'targetParameters': ['System.Collections.Generic.IEnumerable`1[System.String]'],
            'kind': 'postfix', 'patchType': patch_type, 'patchMethod': 'Postfix'}


HARMONY_OK = patch('rwmodtest.harmonyok', 'RWMT.HarmonyOk.ToSpaceListPatch')
HARMONY_MISSING = patch('rwmodtest.harmonymissing', 'RWMT.HarmonyMissing.ToSpaceListPatch')


def case(levels, mods, expectations=None, *, official=('Core',), language='English', limits=None, tests=None):
    request = {'recordType': 'modValidationRequest', 'schemaVersion': 1, 'levels': list(levels), 'official': list(official),
               'mods': [{'path': name.lstrip('*'), 'target': name.startswith('*')} for name in mods],
               'language': language, 'expectations': expectations or {}}
    if limits:
        request['limits'] = limits
    if tests:
        request['tests'] = tests
    return request


# name -> (request, expected status, reason codes that must be present, runtime)
CASES = {
    'ok': (case('A', ['*okxml'], OK_EXPECTATIONS), 'passed', [], 'waylith'),
    'ok-japanese': (case('A', ['*okxml'], {'keyed': [{'key': 'RWMT_Hello', 'equals': '検証用フィクスチャからこんにちは'}]},
                         language='Japanese'), 'passed', [], 'waylith'),
    'ok-all-dlc-japanese': (case('A', ['*okxml'], OK_EXPECTATIONS | {'keyed': []},
                                 official=('Core', 'Royalty', 'Ideology', 'Biotech', 'Odyssey'), language='Japanese'),
                            'passed', [], 'waylith'),
    'expectation-mismatch': (case('A', ['*okxml'], {'defs': [{'type': 'ThingDef', 'defName': 'RWMT_NotDefined', 'exists': True}]}),
                             'failed', ['expectationMismatch'], 'waylith'),
    'side-effect': (case('A', ['*sideeffect']), 'failed', ['newErrors'], 'waylith'),
    'bad-patch': (case('A', ['*badpatch']), 'failed', ['newErrors'], 'waylith'),
    'bad-reference': (case('A', ['*badref']), 'failed', ['newErrors'], 'waylith'),
    'init-exception': (case('A', ['*initthrow']), 'failed', ['newErrors'], 'waylith'),
    'harmony-ok': (case('AB', ['harmonylib', '*harmonyok'], {'harmonyPatches': [HARMONY_OK]}), 'passed', [], 'waylith'),
    'harmony-missing': (case('AB', ['harmonylib', '*harmonymissing'], {'harmonyPatches': [HARMONY_MISSING]}),
                        'failed', ['harmonyPatchMissing'], 'waylith'),
    'harmony-no-expectation': (case('AB', ['harmonylib', '*harmonyok']), 'incomplete', ['noExpectedPatches'], 'waylith'),
    'harmony-not-provided': (case('AB', ['*harmonyok'], {'harmonyPatches': [HARMONY_OK]}), 'blocked', ['harmonyMissing'], 'waylith'),
    'level-c': (case('ABC', ['harmonylib', '*harmonyok'], {'harmonyPatches': [HARMONY_OK]}, tests=['any']),
                'blocked', ['levelUnsupported'], 'waylith'),
    # All DLCs take longer than the 5 s Worker deadline that a 10 s limit leaves.
    'timeout': (case('A', ['*okxml'], official=('Core', 'Royalty', 'Ideology', 'Biotech', 'Odyssey'),
                     limits={'timeoutSeconds': 10}), 'incomplete', ['workerInterrupted'], 'waylith'),
    'standard-runtime-ok': (case('A', ['*okxml'], OK_EXPECTATIONS), 'incomplete', ['experimental'], 'standard'),
    'standard-runtime-bad-reference': (case('A', ['*badref']), 'incomplete', ['experimental', 'newErrors'], 'standard'),
}


def build_fixtures(out, snapshot, harmony_dll):
    staged = out / 'fixtures'
    if staged.exists():
        shutil.rmtree(staged)
    shutil.copytree(FIXTURES, staged)
    (staged / 'harmonylib' / 'Assemblies').mkdir(exist_ok=True)
    shutil.copyfile(harmony_dll, staged / 'harmonylib' / 'Assemblies' / '0Harmony.dll')
    for mod, project in ASSEMBLIES.items():
        build = out / 'fixture-build' / project
        subprocess.run(['dotnet', 'build', '-c', 'Release', '--nologo', '-v', 'q', str(SOURCES / project / f'{project}.csproj'),
                        f'-p:GameManagedDir={Path(snapshot) / "game"}', f'-p:HarmonyDll={harmony_dll}', '-o', str(build),
                        f'-p:BaseIntermediateOutputPath={out / "fixture-build" / "obj" / project}/'], check=True,
                       stdout=subprocess.DEVNULL)
        (staged / mod / 'Assemblies').mkdir(exist_ok=True)
        shutil.copyfile(build / f'RWMT.{project}.dll', staged / mod / 'Assemblies' / f'RWMT.{project}.dll')
    return staged


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--harmony-dll', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--worker', default=str(REPO / 'worker' / 'bin'))
    parser.add_argument('--cases', help='comma-separated subset')
    args = parser.parse_args(argv)
    out = Path(args.out).resolve()
    if REPO in out.parents or out == REPO:
        parser.error('--out must be outside the repository')
    out.mkdir(parents=True, exist_ok=True)
    staged = build_fixtures(out, args.snapshot, Path(args.harmony_dll).resolve())
    selected = args.cases.split(',') if args.cases else list(CASES)
    rows, ok = [], True
    for name in selected:
        request, expected_status, expected_codes, runtime = CASES[name]
        case_dir = out / 'cases' / name
        if case_dir.exists():
            shutil.rmtree(case_dir)
        case_dir.mkdir(parents=True)
        for mod in request['mods']:
            mod['path'] = str(staged / mod['path'])
        request_path = case_dir / 'request.json'
        request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding='utf-8')
        started = time.monotonic()
        result = validation_host.run_validation(args.snapshot, request_path, case_dir / 'out', args.worker, runtime=runtime,
                                                baseline_cache=out / 'baseline-cache')
        codes = [r['code'] for r in result.get('reasons', [])]
        good = result['status'] == expected_status and all(c in codes for c in expected_codes)
        ok &= good
        rows.append({'case': name, 'runtime': runtime, 'expected': expected_status, 'status': result['status'],
                     'executionStatus': result['executionStatus'], 'fidelity': result.get('fidelity'), 'reasons': codes,
                     'newDiagnostics': [e['message'].splitlines()[0][:160] for e in (result.get('diagnostics') or {}).get('newInTarget', [])],
                     'baselineCached': (result.get('diagnostics') or {}).get('baselineCached'),
                     'seconds': round(time.monotonic() - started, 2), 'timings': result.get('timings'), 'ok': good})
        print(f'{"OK " if good else "BAD"} {name:32} {result["status"]:10} {",".join(codes):60} {rows[-1]["seconds"]:7.2f}s', flush=True)
    (out / 'matrix.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'matrix: {out / "matrix.json"}')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
