"""Public boundary: stale, partial, hostile evidence must never become success."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import private_validation as pv

IDENTITY = {'runId': '100-1', 'commit': 'a' * 40}
ENV = {'GITHUB_REPOSITORY': 'pengin0503/RimWorld-for-mod-test',
       'GITHUB_REF': 'refs/heads/main', 'GITHUB_SHA': 'a'*40,
       'GITHUB_RUN_ID': '100', 'GITHUB_RUN_ATTEMPT': '1'}


def raw(selection='smoke'):
    return {**IDENTITY, 'selection': selection, 'suites': [
        {'suite': n, 'started': True, 'blocked': False, 'demonstratedFailure': False,
         'processes': [{'exitCode': 0, 'interrupted': False, 'seconds': .1}] * (2 if n == 'c-regression' else 1),
         'checks': {'complete': True, 'accepted': True, 'qualified': n == 'smoke'}}
        for n in pv.resolve_suites(selection)]}


class SummaryTests(unittest.TestCase):
    def test_registry_rejects_untrusted_selection(self):
        self.assertEqual(pv.resolve_suites('cow'), ('cow',))
        self.assertEqual(pv.resolve_suites('all'), ('smoke','c-regression','d-regression','d-compare','cow'))
        for n in ('PRIVATE', '../cow', '', None):
            with self.subTest(n=n), self.assertRaises(ValueError): pv.resolve_suites(n)

    def test_identity_rejects_branch_and_wrong_repo_before_any_work(self):
        self.assertEqual(pv.current_identity(ENV), IDENTITY)
        for key, value in [('GITHUB_REF','refs/heads/PRIVATE'), ('GITHUB_REPOSITORY','other/repo'),
                           ('GITHUB_SHA','PRIVATE'), ('GITHUB_RUN_ATTEMPT','0')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                pv.current_identity({**ENV,key:value})

    def test_only_whitelisted_fields_are_published(self):
        data = raw(); data['secret'] = 'PRIVATE'
        data['suites'][0]['exception'] = 'PRIVATEException'
        data['suites'][0]['processes'][0].update(path='PRIVATE', seconds=float('nan'))
        public = pv.public_summary(data, IDENTITY)
        encoded = json.dumps(public, allow_nan=False)
        self.assertNotIn('PRIVATE', encoded)
        self.assertIsNone(public['suites'][0]['processes'][0]['seconds'])
        self.assertTrue(public['acceptancePassed'])

    def test_stale_identity_or_wrong_selection_never_passes(self):
        for change in ({'runId':'99-1'}, {'commit':'b'*40}, {'selection':'cow'}):
            data = raw(); data.update(change)
            self.assertFalse(pv.public_summary(data, IDENTITY)['acceptancePassed'])

    def test_missing_duplicate_and_interrupted_rows_cannot_pass(self):
        data = raw('all')
        for rows in (data['suites'][:-1], data['suites']+[data['suites'][0]]):
            self.assertFalse(pv.public_summary({**data,'suites':rows}, IDENTITY)['acceptancePassed'])
        data['suites'][-1]['processes'][0]['interrupted'] = True
        self.assertFalse(pv.public_summary(data, IDENTITY)['acceptancePassed'])

    def test_completed_suite_is_preserved_after_later_cancellation(self):
        data = raw('all'); data['suites'] = data['suites'][:1]
        public = pv.public_summary(data, IDENTITY)
        self.assertFalse(public['acceptancePassed'])
        self.assertEqual(public['suites'][0]['validationStatus'], 'passed')
        self.assertEqual(public['suites'][1]['executionStatus'], 'notStarted')

    def test_regression_acceptance_does_not_qualify_c_or_d(self):
        for n in ('c-regression','d-regression','d-compare'):
            public = pv.public_summary(raw(n), IDENTITY)
            self.assertTrue(public['acceptancePassed'])
            self.assertEqual(public['validationStatus'], 'incomplete')
            self.assertEqual(public['qualificationStatus'], 'experimental')

    def test_failed_and_blocked_are_distinguished(self):
        data = raw(); data['suites'][0]['demonstratedFailure'] = True
        data['suites'][0]['checks']['accepted'] = False
        self.assertEqual(pv.public_summary(data, IDENTITY)['validationStatus'], 'failed')
        data['suites'][0].update(blocked=True, started=False, processes=[], checks={})
        self.assertEqual(pv.public_summary(data, IDENTITY)['validationStatus'], 'blocked')

    def test_session_reinit_invalidates_previous_success(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, ENV, clear=True):
            root=Path(d); session=pv.init_session(root,'smoke')
            pv.write_json(session/'summary.json',raw())
            self.assertTrue(pv.publish_session(root)['acceptancePassed'])
            with self.assertRaises(ValueError): pv.init_session(root,'smoke')
            self.assertFalse(pv.publish_session(root)['acceptancePassed'])

    def test_publish_rechecks_manifest_selection(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, ENV, clear=True):
            root=Path(d); session=pv.init_session(root,'cow')
            pv.write_json(session/'summary.json',raw())
            self.assertFalse(pv.publish_session(root)['acceptancePassed'])


class CheckpointPublicationTests(unittest.TestCase):
    def test_publisher_uses_latest_partial_execution_checkpoint(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, ENV, clear=True):
            root=Path(d); session=pv.init_session(root,'all')
            manifest=pv.read_json(session/'session.json'); manifest['executionAttempted']=True
            pv.write_json(session/'session.json',manifest)
            (session/'execution').mkdir()
            data=raw('all'); data['suites']=data['suites'][:1]
            pv.write_json(session/'execution/summary.json',data)
            public=pv.publish_session(root)
            self.assertEqual(public['suites'][0]['validationStatus'],'passed')
            self.assertFalse(public['acceptancePassed'])
