"""Contract tests for non-rendered event choice observations."""
import unittest
from pathlib import Path
from tools import validation_host as vh

CASE = 'event-choice.v1'
EXPECTED = {'event': 'RWMT_ChoiceEvent', 'choice': 'accept', 'rewardThing': 'Steel', 'rewardCount': 10}


ACTUAL = {'eventOccurred': True, 'choicePresented': True, 'choiceExecuted': True,
          'rewardThing': 'Steel', 'rewardCount': 10, 'rewardSource': 'mapItemStackDelta',
          'mapDeltaUnambiguous': True, 'context': 'freshGeneratedMap', 'rendered': False}

def request():
    return {'recordType': 'modValidationRequest', 'schemaVersion': 1, 'levels': ['A', 'C'],
            'mods': [{'path': 'mod', 'target': True}], 'map': {'seed': 'RWMT-event'},
            'tests': [CASE], 'expectations': {'eventChoices': [dict(EXPECTED)]}}


class EventRequestTests(unittest.TestCase):
    def test_event_case_is_accepted_with_fixed_map_and_expected_reward(self):
        result = vh.validate_request(request(), Path('/tmp'))
        self.assertEqual(result['expectations']['eventChoices'], [EXPECTED])

    def test_invalid_event_requests_are_refused(self):
        for variant in (dict(request(), map=None), dict(request(), tests=[]),
                        dict(request(), expectations={'eventChoices': []}),
                        dict(request(), expectations={'eventChoices': [dict(EXPECTED, rewardCount=True)]}),
                        dict(request(), expectations={'eventChoices': [dict(EXPECTED, choice='../escape')]}),
                        dict(request(), expectations={'eventChoices': [dict(EXPECTED, event='OtherIncident')]})):
            with self.subTest(variant=variant), self.assertRaises(vh.RequestError):
                vh.validate_request(variant, Path('/tmp'))

class EventEvaluationTests(unittest.TestCase):
    def test_missing_observation_remains_incomplete(self):
        stage, reasons, failed = vh.evaluate_event_choice({'expectations': {'eventChoices': [EXPECTED]}}, {})
        self.assertEqual(stage['status'], 'incomplete')
        self.assertIn('eventChoiceObservationIncomplete', [r['code'] for r in reasons])
        self.assertFalse(failed)

    def test_matching_observation_is_experimental(self):
        actual = dict(ACTUAL)
        row = {'caseId': CASE, 'expected': EXPECTED, 'actual': actual}
        stage, reasons, failed = vh.evaluate_event_choice({'expectations': {'eventChoices': [EXPECTED]}}, {'eventChoices': [row]})
        self.assertEqual(stage['status'], 'completed')
        self.assertIn('cNotQualified', [r['code'] for r in reasons])
        self.assertFalse(failed)

    def test_reward_mismatch_is_failed_and_missing_execution_is_incomplete(self):
        r = {'expectations': {'eventChoices': [EXPECTED]}}
        actual = dict(ACTUAL, rewardCount=9)
        row = {'caseId': CASE, 'expected': EXPECTED, 'actual': actual}
        stage, _, failed = vh.evaluate_event_choice(r, {'eventChoices': [row]})
        self.assertEqual(stage['status'], 'failed')
        self.assertEqual(failed[0]['code'], 'eventChoiceMismatch')
        actual['choiceExecuted'] = False
        stage, reasons, failed = vh.evaluate_event_choice(r, {'eventChoices': [row]})
        self.assertEqual(stage['status'], 'incomplete')
        self.assertIn('eventChoiceObservationIncomplete', [x['code'] for x in reasons])
        self.assertFalse(failed)

    def test_rejects_wrong_identity_and_nonboolean_execution_evidence(self):
        r = {'expectations': {'eventChoices': [EXPECTED]}}
        actual = dict(ACTUAL, choiceExecuted=1)
        for row in ({'caseId': CASE, 'expected': EXPECTED, 'actual': actual},
                    {'caseId': 'other', 'expected': EXPECTED, 'actual': dict(actual, choiceExecuted=True)}):
            stage, _, _ = vh.evaluate_event_choice(r, {'eventChoices': [row]})
            self.assertEqual(stage['status'], 'incomplete')

    def test_real_map_delta_provenance_is_required(self):
        r = {'expectations': {'eventChoices': [EXPECTED]}}
        for invalid in (
            {'rewardSource': 'fixtureStaticFields'},
            {'rewardSource': None},
            {'mapDeltaUnambiguous': False},
            {'mapDeltaUnambiguous': 1},
            {'rewardThing': None, 'rewardCount': 10},
            {'rewardThing': 'Steel', 'rewardCount': 0},
            {'rewardCount': True},
        ):
            with self.subTest(invalid=invalid):
                actual = dict(ACTUAL, **invalid)
                row = {'caseId': CASE, 'expected': EXPECTED, 'actual': actual}
                stage, reasons, failed = vh.evaluate_event_choice(r, {'eventChoices': [row]})
                self.assertEqual(stage['status'], 'incomplete')
                self.assertIn('eventChoiceObservationIncomplete', [x['code'] for x in reasons])
                self.assertFalse(failed)

    def test_observed_no_spawn_is_a_mismatch_not_an_unverified_success(self):
        r = {'expectations': {'eventChoices': [EXPECTED]}}
        actual = dict(ACTUAL, rewardThing=None, rewardCount=0)
        row = {'caseId': CASE, 'expected': EXPECTED, 'actual': actual}
        stage, reasons, failed = vh.evaluate_event_choice(r, {'eventChoices': [row]})
        self.assertEqual(stage['status'], 'failed')
        self.assertIn('cNotQualified', [x['code'] for x in reasons])
        self.assertEqual(failed[0]['code'], 'eventChoiceMismatch')

    def test_observed_other_reward_is_a_mismatch(self):
        r = {'expectations': {'eventChoices': [EXPECTED]}}
        actual = dict(ACTUAL, rewardThing='WoodLog', rewardCount=10)
        row = {'caseId': CASE, 'expected': EXPECTED, 'actual': actual}
        stage, _, failed = vh.evaluate_event_choice(r, {'eventChoices': [row]})
        self.assertEqual(stage['status'], 'failed')
        self.assertEqual(failed[0]['code'], 'eventChoiceMismatch')
