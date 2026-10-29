"""Run the self-made event-choice fixture in a private game snapshot.

An exit code of zero confirms these fixture observations only; C remains experimental.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from tools import validation_host as vh


def missing_fixture_confirmed(result):
    codes = {r['code'] for r in result.get('reasons', [])}
    return (result['status'] == 'incomplete' and result['executionStatus'] == 'completed'
            and result.get('stages', {}).get('C', {}).get('status') == 'incomplete'
            and 'eventChoiceObservationIncomplete' in codes
            and codes <= {'experimental', 'cNotQualified', 'mapNotQualified',
                          'eventChoiceObservationIncomplete'})


def record_result(out, rows, name, ok, result):
    rows.append({"case":name,"ok":bool(ok),"status":result.get("status"),
                 "stage":result.get("stages",{}).get("C",{}).get("status")})
    (out / "summary.json").write_text(json.dumps(rows),encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--worker', default=str(REPO / 'worker/bin'))
    parser.add_argument('--dotnet', default='dotnet')
    args = parser.parse_args()
    out = Path(args.out).resolve()
    if out == REPO or REPO in out.parents or out.exists():
        parser.error('--out must be a new directory outside the checkout')
    game = Path(args.snapshot).resolve() / 'game'
    assemblies = list(game.rglob('Assembly-CSharp.dll'))
    if len(assemblies) != 1:
        parser.error('snapshot must contain exactly one game assembly')
    out.mkdir(parents=True, mode=0o700)
    fixture = out / 'fixture'
    shutil.copytree(REPO / 'tests/fixtures/validation-mods/eventchoice', fixture)
    build = [args.dotnet, 'build', str(REPO / 'tests/fixtures/validation-mods-src/EventChoice'),
             '-c', 'Release', '-o', str(fixture / 'Assemblies'),
             f'-p:GameManagedDir={assemblies[0].parent}', '--nologo']
    with (out / 'build.log').open('w', encoding='utf-8') as log:
        if subprocess.run(build, stdout=log, stderr=subprocess.STDOUT, check=False).returncode:
            print('fixture build failed; inspect the private build log', file=sys.stderr)
            return 1
    request = {'recordType': 'modValidationRequest', 'schemaVersion': 1, 'levels': ['A', 'C'],
               'mods': [{'path': str(fixture), 'target': True}], 'map': {'seed': 'RWMT-event'},
               'tests': ['event-choice.v1'], 'expectations': {'eventChoices': [
                   {'event': 'RWMT_ChoiceEvent', 'choice': 'accept', 'rewardThing': 'Steel', 'rewardCount': 10}]}}
    path = out / 'request.json'
    path.write_text(json.dumps(request), encoding='utf-8')
    result = vh.run_validation(args.snapshot, path, out / 'result', args.worker,
                               baseline_cache=out / 'baseline-cache')
    reasons = {reason['code'] for reason in result['reasons']}
    stage = result.get('stages', {}).get('C', {})
    ok = (result['status'] == 'incomplete' and result['executionStatus'] == 'completed'
          and stage.get('status') == 'completed' and 'cNotQualified' in reasons
          and not reasons.intersection({'newErrors', 'newWarnings', 'eventChoiceObservationIncomplete',
                                       'eventChoiceMismatch', 'baselineIncomplete'}))
    print('fixture observations:', 'matched' if ok else 'not confirmed',
          '; overall:', result['status'], '; C:', stage.get('status'))
    rows = []
    record_result(out, rows, 'positive', ok, result)
    # Mutate expectations only: the actual game must still generate Steel 10.
    for name, item, count in [('wrong-count', 'Steel', 11), ('wrong-item', 'WoodLog', 10)]:
        request['expectations']['eventChoices'][0].update(rewardThing=item, rewardCount=count)
        path.write_text(json.dumps(request), encoding='utf-8')
        negative = vh.run_validation(args.snapshot, path, out / name, args.worker,
                                     baseline_cache=out / 'baseline-cache')
        codes = {r['code'] for r in negative.get('reasons', [])}
        matched = (negative['status'] == 'incomplete' and negative['executionStatus'] == 'completed'
                   and negative.get('stages', {}).get('C', {}).get('status') == 'failed'
                   and 'eventChoiceMismatch' in codes
                   and not codes.intersection({'newErrors', 'newWarnings', 'baselineIncomplete',
                                               'eventChoiceObservationIncomplete'}))
        record_result(out, rows, name, matched, negative)
        ok = ok and matched
        print(name, 'detected' if matched else 'not confirmed')
    missing = out / 'missing-fixture'
    shutil.copytree(REPO / 'tests/fixtures/validation-mods/okxml', missing)
    request['mods'] = [{'path': str(missing), 'target': True}]
    request['expectations']['eventChoices'][0].update(rewardThing='Steel', rewardCount=10)
    path.write_text(json.dumps(request), encoding='utf-8')
    absent = vh.run_validation(args.snapshot, path, out / 'missing', args.worker,
                               baseline_cache=out / 'baseline-cache')
    matched = missing_fixture_confirmed(absent)
    record_result(out, rows, 'missing-fixture', matched, absent)
    ok = ok and matched
    print('missing fixture', 'incomplete as required' if matched else 'not confirmed')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())

