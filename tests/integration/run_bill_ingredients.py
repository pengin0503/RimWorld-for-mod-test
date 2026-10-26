"""Private actual-game C smoke/regression cases. Public repository contains only our fixture.

No drawing and no tick; cached snapshot only. Results and raw logs must remain outside checkout.
Exit 0 means the observations/status guards matched, NOT that C is qualified or rendering passed.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from tools import validation_host as vh

CASE = 'bill-ingredient-options.v1'


def ingredient(recipe, thing, visible, allowed):
    return dict(recipe=recipe, thing=thing, visible=visible, allowed=allowed)


CASES = {
    'positive': ([ingredient('RWMT_BillHidden', 'RWMT_BillGrain', False, True),
                  ingredient('RWMT_BillOptions', 'RWMT_BillGrain', True, True),
                  ingredient('RWMT_BillOptions', 'RawCorn', True, False),
                  ingredient('RWMT_BillOptions', 'RawPotatoes', False, False)], 'completed', []),
    'hidden-fault': ([ingredient('RWMT_BillHidden', 'RWMT_BillGrain', True, True)], 'failed', ['billIngredientMismatch']),
    'fixed-pane': ([ingredient('RWMT_BillFixed', 'RWMT_BillGrain', False, True)], 'incomplete',
                   ['billIngredientObservationIncomplete']),
    'outside-tree': ([ingredient('RWMT_BillOptions', 'Steel', False, False)], 'incomplete',
                     ['billIngredientObservationIncomplete']),
    'missing-thing': ([ingredient('RWMT_BillOptions', 'RWMT_MissingThing', False, False)], 'incomplete',
                      ['billIngredientObservationIncomplete']),
    'missing-def': ([ingredient('RWMT_MissingRecipe', 'RWMT_BillGrain', False, False)], 'incomplete',
                    ['billIngredientObservationIncomplete']),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--worker', default=str(REPO / 'worker/bin'))
    args = parser.parse_args()
    out = Path(args.out).resolve()
    if out == REPO or REPO in out.parents or out.exists():
        parser.error('--out must be a new directory outside checkout')
    out.mkdir(parents=True)
    fixture = out / 'fixture'
    shutil.copytree(REPO / 'tests/fixtures/validation-mods/billingredients', fixture)
    rows = []
    for name, (expected, stage, codes) in CASES.items():
        request = {'recordType': 'modValidationRequest', 'schemaVersion': 1, 'levels': ['A', 'C'],
                   'mods': [{'path': str(fixture), 'target': True}], 'tests': [CASE],
                   'expectations': {'billIngredients': expected}}
        request_file = out / f'{name}.json'
        request_file.write_text(json.dumps(request))
        result = vh.run_validation(args.snapshot, request_file, out / name, args.worker,
                                   baseline_cache=out / 'baseline-cache')
        actual_codes = [r['code'] for r in result['reasons']]
        actual_stage = result['stages'].get('C', {}).get('status')
        ok = (result['status'] == 'incomplete' and result['executionStatus'] == 'completed'
              and actual_stage == stage and all(c in actual_codes for c in ['cNotQualified', *codes]))
        # Do not let load diagnostics accidentally satisfy this behavioral test.
        ok = ok and not any(c in actual_codes for c in ('newErrors', 'newWarnings', 'baselineIncomplete', 'checkError'))
        observations = (result.get('checks') or {}).get('billIngredients') or []
        if name == 'positive' and observations:
            hidden = observations[0].get('actual') or {}
            ok = ok and hidden.get('parentAllows') is True and hidden.get('specialFilterDisallows') is True
            ok = ok and hidden.get('visible') is False and hidden.get('allowed') is True
        expected_reason = {'fixed-pane': 'paneNotEditable', 'missing-def': 'defMissing',
                           'missing-thing': 'defMissing', 'outside-tree': 'categoryMissing'}.get(name)
        if expected_reason:
            ok = ok and len(observations) == 1 and observations[0].get('reason') == expected_reason
        rows.append(dict(case=name, ok=ok, status=result['status'], stage=actual_stage, codes=actual_codes))
        print(json.dumps(rows[-1]), flush=True)
    (out / 'summary.json').write_text(json.dumps(rows, indent=2))
    return 0 if all(r['ok'] for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
