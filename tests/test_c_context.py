import copy
import json
import unittest
from tools import c_context_evidence as context
from tools import private_validation as pv
from unittest.mock import patch
from pathlib import Path
import tempfile
import importlib.util


class ContextTests(unittest.TestCase):
    def helper(self):
        path = Path(__file__).resolve().parents[1]/'experiments/official-comparison/probe_c_context.py'
        spec = importlib.util.spec_from_file_location('probe_c_context', path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module
    def evidence(self):
        return {'rows': [{'phase': 'generated', 'seq': 1, 'sameGame': True, 'sameMap': True, 'finalizeCalls': 0},
                         {'phase': 'marker', 'seq': 2, 'sameGame': True, 'sameMap': True, 'finalizeCalls': 0}],
                'exitCode': 0, 'interrupted': False, 'errors': []}

    def test_event_requires_marker_before_finalize_in_each_context(self):
        product = self.evidence(); official = self.evidence()
        self.assertTrue(context.event_gate(product, official)['gatePassed'])
        official['rows'].insert(1, {'phase': 'finalize', 'seq': 2, 'sameGame': True, 'sameMap': True, 'finalizeCalls': 1})
        official['rows'][-1].update(seq=3, finalizeCalls=1)
        result = context.event_gate(product, official)
        self.assertFalse(result['gatePassed'])
        self.assertIn('official.finalizedBeforeMarker', result['stopReasons'])
        self.assertFalse(result['c0Passed'])

    def test_missing_duplicate_interrupted_changed_context_and_diagnostics_reject(self):
        for change in ({'rows': []}, {'rows': self.evidence()['rows']*2}, {'interrupted': True},
                       {'exitCode': 1}, {'errors': ['PRIVATE']},
                       {'rows': [{**r, 'sameGame': False} for r in self.evidence()['rows']]}):
            with self.subTest(change=change):
                result = context.event_gate(self.evidence(), {**self.evidence(), **change})
                self.assertFalse(result['gatePassed'])
                self.assertNotIn('PRIVATE', json.dumps(result))

    def test_bool_sequence_unknown_phases_and_extra_fields_are_rejected(self):
        for change in ({'seq': True}, {'phase': 'PRIVATE'}, {'extra': 'PRIVATE'}):
            evidence = self.evidence(); evidence['rows'][0].update(change)
            result = context.event_gate(evidence, self.evidence())
            self.assertFalse(result['gatePassed'])
            self.assertNotIn('PRIVATE', json.dumps(result))

    def test_material_requires_real_row_reachability_and_exception_free_return(self):
        row = {'freshGame': True, 'newBill': True, 'pane': 1, 'ui': 1, 'listing': 1, 'row': 1,
               'returned': True, 'exception': False, 'allowed': True}
        evidence = {'rows': [{'phase': 'material', **row}], 'exitCode': 0, 'interrupted': False, 'errors': []}
        self.assertTrue(context.material_gate(evidence)['gatePassed'])
        for change in ({'row': 0}, {'exception': True}, {'returned': False}, {'freshGame': False}, {'row': True}):
            other = copy.deepcopy(evidence); other['rows'][0].update(change)
            self.assertFalse(context.material_gate(other)['gatePassed'])

    def test_finalize_after_marker_is_outside_observation_context(self):
        official = self.evidence()
        official['rows'].append({'phase': 'finalize', 'seq': 3, 'sameGame': True, 'sameMap': True, 'finalizeCalls': 1})
        self.assertTrue(context.event_gate(self.evidence(), official)['gatePassed'])

    def test_parser_retains_errors_before_marker_but_not_shutdown_after_it(self):
        marker = '[RWMT-CONTEXT] '+json.dumps(self.evidence()['rows'][-1])
        parsed = context.parse_lines(['2026-10-30 00:00:00.000 ERROR [Verse] PRIVATE', marker,
                                      '2026-10-30 00:00:00.001 ERROR [Verse] shutdown'], worker=False)
        self.assertEqual(parsed['errors'], ['PRIVATE'])
        self.assertEqual(len(parsed['rows']), 1)
        self.assertEqual(len(context.parse_lines(['[RWMT-CONTEXT] invalid'], worker=False)['errors']), 1)

    def test_supervisor_checks_private_player_log_even_after_fast_exit(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); log = root/'stdout.log'; player = root/'Player.log'
            with player.open('wb') as stream:
                stream.truncate(8*1024*1024+1)
            def launch(*args, **kwargs):
                pv.write_json(log.with_suffix('.guardian.json'), {'exitCode': 0, 'strayProcessesKilled': False})
                class Process:
                    returncode = 0
                    def poll(self): return 0
                    def wait(self): return 0
                return Process()
            with patch.object(pv, 'native_process_available', return_value=True), patch.object(pv.subprocess, 'Popen', side_effect=launch):
                result = pv.run_command(['unused'], log, timeout=1, watch_paths=(player,))
            self.assertTrue(result['interrupted'])

    def test_context_suite_is_explicit_and_cannot_qualify_or_inject_names(self):
        self.assertEqual(pv.resolve_suites('c-context'), ('c-context',))
        self.assertNotIn('c-context', pv.resolve_suites('all'))
        identity = {'runId': '100-1', 'commit': 'a'*40}
        cases = [context.material_gate({'rows': [], 'exitCode': 0, 'interrupted': False, 'errors': []}),
                 context.event_gate(self.evidence(), self.evidence())]
        for row in cases: row['executionStatus'] = 'completed'
        checks = {'complete': True, 'accepted': False, 'contextCases': cases}
        raw = {**identity, 'selection': 'c-context', 'suites': [{'suite': 'c-context', 'started': True,
            'processes': [{'exitCode': 1, 'interrupted': False, 'seconds': 1}], 'checks': checks}]}
        result = pv.public_summary(raw, identity)
        self.assertEqual(len(result['suites'][0]['contextCases']), 2)
        self.assertEqual(result['qualificationStatus'], 'experimental')
        cases[0]['stopReasons'] = ['PRIVATE']
        self.assertNotIn('PRIVATE', json.dumps(pv.public_summary(raw, identity)))

    def test_product_process_status_is_adapted_from_controller_result(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d)/'events.jsonl'; log.write_text('')
            result = {'executionStatus': 'completed', 'stages': {'C': {'status': 'completed'}},
                      'process': {'target': {'exitCode': 0}}, 'reasons': [{'code': 'cNotQualified'}]}
            m = self.helper()
            self.assertFalse(m.product_evidence(result, log)['interrupted'])
            self.assertTrue(m.product_ready(result))
            result['reasons'].append({'code': 'newErrors'})
            self.assertFalse(m.product_ready(result))

    def test_context_protocol_cannot_accept_missing_proof_or_promote_qualification(self):
        from tools.private_validation_evidence import inspect
        material = {'rows': [{'phase': 'material', 'freshGame': True, 'newBill': True, 'pane': 1,
            'ui': 1, 'listing': 1, 'row': 1, 'returned': True, 'exception': False, 'allowed': True}],
            'exitCode': 0, 'interrupted': False, 'errors': []}
        rows = [context.material_gate(material), context.event_gate(self.evidence(), self.evidence())]
        for row in rows: row['executionStatus'] = 'completed'
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            pv.write_json(out/'safe-summary.json', {'schemaVersion': 1, 'c0Passed': False, 'cases': rows})
            checked = inspect('c-context', out)
            self.assertTrue(checked['accepted'])
            self.assertFalse(checked['qualified'])
            del rows[0]['reachability']
            pv.write_json(out/'safe-summary.json', {'schemaVersion': 1, 'c0Passed': False, 'cases': rows})
            self.assertFalse(inspect('c-context', out)['accepted'])

    def test_context_requires_harmony_without_adding_it_to_default_all(self):
        from tests.test_private_validation import ENV
        with tempfile.TemporaryDirectory() as d, patch.dict(pv.os.environ, ENV, clear=True):
            path = pv.init_session(Path(d), 'c-context')
            self.assertTrue(pv.read_json(path/'session.json')['needsHarmony'])
        commands = pv.suite_commands('c-context', Path('/snapshot'), Path('/out'), Path('/worker'), harmony=Path('/harmony'))
        self.assertEqual(len(commands), 1)
        self.assertIn('probe_c_context.py', commands[0][0][1])

    def test_build_diagnostics_expose_only_our_source_id_line_and_compiler_code(self):
        text = '/PRIVATE/CContext.cs(12,4): error CS0012: PRIVATE.secret\n/PRIVATE/Secret.cs(1,1): error CS1234: PRIVATE\n'
        self.assertEqual(self.helper().build_diagnostics(text), [{'source': 'CContext', 'line': 12, 'code': 'CS0012'}])

    def test_fixed_diagnostic_tags_and_setup_stage_do_not_expose_private_text(self):
        summary = context.diagnostic_summary({'exitCode': 0, 'interrupted': False,
            'errors': ['PRIVATE dependency downloadUrl missing', 'PRIVATE graphics exception']})
        self.assertEqual(summary['errorCount'], 2)
        self.assertIn('dependency', summary['kinds'][0])
        self.assertNotIn('PRIVATE', json.dumps(summary))
        self.assertIn('Steam', context.diagnostic_summary({'exitCode': 0, 'interrupted': False,
            'errors': ['PRIVATE Steam startup failure']})['kinds'][0])
        row = {'phase': 'material', 'freshGame': True, 'newBill': True, 'pane': 0,
               'ui': 0, 'listing': 0, 'row': 0, 'returned': False, 'exception': True,
               'allowed': False, 'setupStage': 'dialog', 'exceptionKind': 'nullReference'}
        result = context.material_gate({'rows': [row], 'exitCode': 0, 'interrupted': False, 'errors': []})
        self.assertEqual(result.get('setupStage'), 'dialog')
        self.assertEqual(result.get('exceptionKind'), 'nullReference')
        row['exceptionKind'] = 'PRIVATE'
        self.assertNotIn('PRIVATE', json.dumps(context.material_gate({'rows': [row], 'exitCode': 0, 'interrupted': False, 'errors': []})))
