"""Controller contract tests; synthetic Worker observations do not qualify game behavior."""
import json
import unittest
from tools import validation_host as vh
from tests import test_validation_host as tvh

CASE = 'bill-ingredient-options.v1'
ITEM = {'recipe': 'RWMT_Cook', 'thing': 'RawRice', 'visible': True, 'allowed': True}


def request():
    return {'recordType': 'modValidationRequest', 'schemaVersion': 1, 'levels': ['A', 'C'],
            'mods': [{'path': 'mod', 'target': True}], 'tests': [CASE],
            'expectations': {'billIngredients': [dict(ITEM)]}}


def observation(**actual):
    values = dict(paneEligible=True, categoryReachable=True, categoryVisible=True, itemVisible=True,
                  visible=True, allowed=True, hiddenByDiscovery=False, parentAllows=True, specialFilterDisallows=False,
                  context='freshGameNewBill', rendered=False, reasons=[])
    values.update(actual)
    return {'caseId': CASE, 'expected': dict(ITEM), 'actual': values, 'outcome': 'match'}


class BillRequestTests(unittest.TestCase):
    def test_accepts_typed_case(self):
        r = vh.validate_request(request(), vh.Path('/tmp'))
        self.assertEqual(r['expectations']['billIngredients'], [ITEM])

    def test_rejects_unknown_empty_duplicate_and_unbounded_cases(self):
        r = request()
        variants = [dict(r, tests=['arbitrary.method']), dict(r, tests=[CASE, CASE]), dict(r, tests=[]),
                    dict(r, levels=['A']), dict(r, expectations={}),
                    dict(r, expectations={'billIngredients': [ITEM, ITEM]}),
                    dict(r, expectations={'billIngredients': [dict(ITEM, recipe=f'R{i}') for i in range(129)]})]
        for item in [dict(ITEM, visible=1), dict(ITEM, allowed='true'), dict(ITEM, recipe='../R'),
                     dict(ITEM, thing='x' * 129), dict(ITEM, arbitrary='call')]:
            variants.append(dict(r, expectations={'billIngredients': [item]}))
        for value in variants:
            with self.subTest(value=value):
                with self.assertRaises(vh.RequestError):
                    vh.validate_request(value, vh.Path('/tmp'))


class BillEvaluationTests(unittest.TestCase):
    def evaluate(self, observations, **options):
        r = vh.validate_request(request(), vh.Path('/tmp'))
        w = tvh.worker_result()
        w['checks']['billIngredients'] = observations
        return vh.evaluate(r, tvh.EvaluationTests.mods, w, None, [], tvh.worker_result(), None, [], {},
                           options.get('fidelity', 'qualified'))

    def test_unqualified_c_never_passes_using_a_qualification(self):
        status, execution, reasons, stages, _ = self.evaluate([observation()])
        self.assertEqual((status, execution), ('incomplete', 'completed'))
        self.assertIn('cNotQualified', [r['code'] for r in reasons])
        self.assertEqual(stages['C']['fidelity'], 'experimental')
        self.assertEqual(stages['C']['status'], 'completed')

    def test_compares_booleans_in_controller_instead_of_trusting_worker_outcome(self):
        result = self.evaluate([observation(visible=False, itemVisible=False, reasons=['itemNotVisible'])])
        self.assertIn('billIngredientMismatch', [r['code'] for r in result[2]])
        self.assertEqual(result[3]['C']['status'], 'failed')

    def test_api_unavailable_blocks_c_without_hiding_completed_load(self):
        result = self.evaluate([dict(observation(), outcome='error', reason='apiUnavailable')])
        self.assertEqual(result[0:2], ('blocked', 'completed'))
        self.assertEqual(result[3]['C']['status'], 'blocked')
        self.assertIn('billIngredientApiUnavailable', [r['code'] for r in result[2]])

    def test_ui_predicate_override_is_observed_without_reimplementing_it(self):
        # A MOD may intentionally override Visible even when a special filter disallows the item.
        result = self.evaluate([observation(specialFilterDisallows=True, reasons=['specialFilterDisallows'])])
        self.assertEqual(result[3]['C']['status'], 'completed')

    def test_rejects_missing_or_contradictory_context_and_filter_evidence(self):
        variants = [observation(context='existingSave'), observation(rendered=True), observation(parentAllows='bad'),
                    observation(specialFilterDisallows=None), observation(parentAllows=False),
                    observation(specialFilterDisallows=True)]
        for key in ('context', 'rendered', 'parentAllows', 'specialFilterDisallows'):
            row = observation()
            del row['actual'][key]
            variants.append(row)
        for row in variants:
            with self.subTest(row=row):
                result = self.evaluate([row])
                self.assertEqual(result[3]['C']['status'], 'incomplete')
                self.assertIn('billIngredientObservationIncomplete', [r['code'] for r in result[2]])

    def test_missing_duplicate_other_identity_and_invalid_context_are_incomplete(self):
        variants = [[], [observation(), observation()], [dict(observation(), caseId='other')],
                    [dict(observation(), expected=dict(ITEM, thing='Steel'))],
                    [dict(observation(), outcome='error', reason='defMissing')],
                    [observation(paneEligible=False)], [observation(categoryReachable=False)],
                    [observation(allowed=1)], [observation(hiddenByDiscovery=True, visible=True)], [observation(visible=True, itemVisible=False)],
                    [dict(observation(), actual=None)]]
        for rows in variants:
            with self.subTest(rows=rows):
                result = self.evaluate(rows)
                self.assertEqual(result[0], 'incomplete')
                self.assertIn('billIngredientObservationIncomplete', [r['code'] for r in result[2]])
                self.assertEqual(result[3]['C']['status'], 'incomplete')


class BillDispatchTests(tvh.TempCase):
    def test_only_target_worker_receives_case_expectations(self):
        self.fx.prepare()
        self.fx.mod('one')
        result, out = self.fx.run(['*one'], levels=['A', 'C'], tests=[CASE],
                                  expectations={'billIngredients': [ITEM]}, keep_run_dirs=True)
        self.assertNotEqual(result['status'], 'blocked', result['reasons'])
        self.assertEqual(result['fidelity'], 'experimental')
        # The real Controller creates these requests; fake Worker is only a subprocess boundary.
        requests = [json.loads(p.read_text()) for p in out.rglob('worker-request.json')]
        self.assertEqual(len(requests), 2)
        counts = sorted(len(r['expectations']['billIngredients']) for r in requests)
        self.assertEqual(counts, [0, 1])
