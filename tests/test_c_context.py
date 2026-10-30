import copy
import json
import unittest
from tools import c_context_evidence as context
from tools import private_validation as pv
from unittest.mock import patch
from pathlib import Path
import tempfile
import importlib.util


def context_row(phase, seq, finalize=0, **change):
    # Fixed observation fields of the event trace; private values never appear here.
    row = {'phase': phase, 'seq': seq, 'sameGame': True, 'sameMap': True, 'finalizeCalls': finalize,
           'mainThread': True, 'programState': 'Entry', 'inLongEvent': True, 'pendingWhenFinished': 0, 'currentMap': False}
    row.update(change)
    return row



class ContextTests(unittest.TestCase):
    def helper(self):
        path = Path(__file__).resolve().parents[1]/'experiments/official-comparison/probe_c_context.py'
        spec = importlib.util.spec_from_file_location('probe_c_context', path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module
    def evidence(self):
        return {'rows': [context_row('generated', 1),
                         context_row('marker', 2)],
                'exitCode': 0, 'interrupted': False, 'errors': []}

    def test_event_requires_marker_before_finalize_in_each_context(self):
        product = self.evidence(); official = self.evidence()
        self.assertTrue(context.event_gate(product, official)['gatePassed'])
        official['rows'].insert(1, context_row('finalize', 2, 1))
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
        official['rows'].append(context_row('finalize', 3, 1))
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
        clean = {'exitCode': 0, 'interrupted': False, 'errorCount': 0, 'kinds': []}
        for row in cases: row.update(executionStatus='completed', diagnostics={'product': clean, 'official': clean})
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
            'ui': 1, 'listing': 1, 'row': 1, 'returned': True, 'exception': False, 'allowed': True,
            'setupStage': 'complete', 'exceptionKind': 'none'}],
            'exitCode': 0, 'interrupted': False, 'errors': []}
        rows = [context.material_gate(material), context.event_gate(self.evidence(), self.evidence())]
        clean = {'exitCode': 0, 'interrupted': False, 'errorCount': 0, 'kinds': []}
        for row in rows: row.update(executionStatus='completed', diagnostics={'product': clean, 'official': clean})
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


class PublicContextAcceptanceTests(unittest.TestCase):
    CLEAN = {'exitCode': 0, 'interrupted': False, 'errorCount': 0, 'kinds': []}

    def passed_rows(self):
        material = {'case': 'material', 'gatePassed': True, 'c0Passed': False, 'stopReasons': [],
                    'executionStatus': 'completed', 'reachability': {'pane': 1, 'ui': 1, 'listing': 1, 'row': 1},
                    'setupStage': 'complete', 'exceptionKind': 'none',
                    'diagnostics': {'product': dict(self.CLEAN), 'official': dict(self.CLEAN)}}
        event = {'case': 'event', 'gatePassed': True, 'c0Passed': False, 'stopReasons': [],
                 'executionStatus': 'completed', 'phases': {'product': ['generated', 'marker'],
                 'official': ['init', 'generated', 'marker']},
                 'diagnostics': {'product': dict(self.CLEAN), 'official': dict(self.CLEAN)}}
        return [material, event]

    def accepted_everywhere(self, rows):
        from tools.private_validation_evidence import inspect
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            pv.write_json(out/'safe-summary.json', {'schemaVersion': 1, 'c0Passed': False, 'cases': rows})
            checked = inspect('c-context', out)
        identity = {'runId': '100-1', 'commit': 'a'*40}
        raw = {**identity, 'selection': 'c-context', 'suites': [{'suite': 'c-context', 'started': True,
            'processes': [{'exitCode': 0, 'interrupted': False, 'seconds': 1}],
            'checks': {'complete': checked['complete'], 'accepted': checked['accepted'], 'contextCases': rows}}]}
        public = pv.public_summary(raw, identity)
        return checked['accepted'], public['acceptancePassed'], public['suites'][0]

    def test_clean_bilateral_success_is_accepted_without_qualification(self):
        rows = self.passed_rows()
        self.assertEqual(len(context.safe_cases(rows)), 2)
        inspected, published, suite = self.accepted_everywhere(rows)
        self.assertTrue(inspected and published)
        self.assertEqual(suite['qualificationStatus'], 'experimental')
        self.assertTrue(all(r['c0Passed'] is False for r in suite['contextCases']))

    def test_success_requires_both_clean_diagnostics(self):
        changes = [('missing', None), ('oneSide', {'product': dict(self.CLEAN)})]
        for key, value in (('exitCode', 1), ('exitCode', None), ('interrupted', True),
                           ('errorCount', 1), ('kinds', [['Steam']])):
            for side in ('product', 'official'):
                changes.append((side + key, {side: {**self.CLEAN, key: value}}))
        for index in (0, 1):
            for name, change in changes:
                with self.subTest(case=index, change=name):
                    rows = self.passed_rows()
                    if change is None: del rows[index]['diagnostics']
                    elif name == 'oneSide': rows[index]['diagnostics'] = change
                    else: rows[index]['diagnostics'].update(change)
                    self.assertEqual(context.safe_cases(rows), [])
                    inspected, published, suite = self.accepted_everywhere(rows)
                    self.assertFalse(inspected or published or suite['acceptancePassed'])

    def test_material_success_requires_completed_setup_without_exception(self):
        for change in ({'setupStage': 'pane'}, {'exceptionKind': 'nullReference'}, {'setupStage': None}):
            with self.subTest(change=change):
                rows = self.passed_rows()
                for key, value in change.items():
                    if value is None: del rows[0][key]; del rows[0]['exceptionKind']
                    else: rows[0][key] = value
                self.assertEqual(context.safe_cases(rows), [])
                self.assertFalse(any(self.accepted_everywhere(rows)[:2]))

    def failed_rows(self):
        rows = self.passed_rows()
        rows[0].update(gatePassed=False, stopReasons=['official.paneDidNotReturn', 'official.treeRowNotReached'],
                       reachability={'pane': 0, 'ui': 0, 'listing': 0, 'row': 0},
                       setupStage='dialog', exceptionKind='missingApi')
        rows[1].update(gatePassed=False, stopReasons=['official.diagnosticsOrExit', 'official.finalizedBeforeMarker'],
                       phases={'product': ['generated', 'marker'], 'official': ['init', 'generated', 'finalize', 'marker']})
        rows[1]['diagnostics']['official'] = {'exitCode': 0, 'interrupted': False, 'errorCount': 2, 'kinds': [['Steam'], []]}
        return rows

    def test_failed_records_remain_published_as_failures(self):
        rows = self.failed_rows()
        safe = context.safe_cases(rows)
        self.assertEqual([r['gatePassed'] for r in safe], [False, False])
        inspected, published, suite = self.accepted_everywhere(rows)
        self.assertFalse(inspected or published)
        self.assertEqual(len(suite['contextCases']), 2)

    def test_legacy_failure_without_diagnostics_is_kept_but_never_promoted(self):
        rows = self.failed_rows()
        for row in rows: del row['diagnostics']
        del rows[0]['setupStage']; del rows[0]['exceptionKind']
        self.assertEqual([r['gatePassed'] for r in context.safe_cases(rows)], [False, False])
        rows[1].update(gatePassed=True, stopReasons=[], phases={'product': ['generated', 'marker'], 'official': ['generated', 'marker']})
        self.assertEqual(context.safe_cases(rows), [])

    def test_contradictory_failure_records_are_rejected(self):
        def material(**change):
            rows = self.failed_rows(); rows[0].update(change); return rows
        def official_diagnostics(case, value, reasons):
            rows = self.failed_rows(); rows[case]['diagnostics']['official'] = value
            rows[case]['stopReasons'] = reasons; return rows
        dirty = {'exitCode': 1, 'interrupted': False, 'errorCount': 0, 'kinds': []}
        cases = {
            'exceptionAtComplete': material(setupStage='complete'),
            'exceptionWithoutPaneStop': material(stopReasons=['official.treeRowNotReached']),
            'countsBeforePane': material(reachability={'pane': 1, 'ui': 0, 'listing': 0, 'row': 0}),
            'completeWithoutException': material(setupStage='complete', exceptionKind='none',
                stopReasons=['official.paneDidNotReturn', 'official.treeRowNotReached']),
            'dirtyWithoutReason': official_diagnostics(1, dirty, ['official.finalizedBeforeMarker']),
            'reasonWithClean': official_diagnostics(0, dict(self.CLEAN),
                ['official.diagnosticsOrExit', 'official.paneDidNotReturn', 'official.treeRowNotReached']),
            'kindsCount': official_diagnostics(1, {'exitCode': 0, 'interrupted': False, 'errorCount': 2, 'kinds': [[]]},
                ['official.diagnosticsOrExit', 'official.finalizedBeforeMarker']),
            'interruptedButCompleted': official_diagnostics(1, {'exitCode': None, 'interrupted': True, 'errorCount': 0, 'kinds': []},
                ['official.diagnosticsOrExit', 'official.finalizedBeforeMarker']),
        }
        rows = self.failed_rows(); rows[1]['diagnostics']['product'] = dirty
        cases['eventProductDirtyWithoutReason'] = rows
        for name, rows in cases.items():
            with self.subTest(name=name):
                self.assertEqual(context.safe_cases(rows), [])

    def test_rows_derived_like_the_probe_are_never_rejected(self):
        # Mirrors probe_c_context.run_case so tightened publication cannot drop genuine records.
        generated = context_row('generated', 1)
        marker = context_row('marker', 2)
        base = {'phase': 'material', 'freshGame': True, 'newBill': True, 'pane': 1, 'ui': 1, 'listing': 1,
                'row': 1, 'returned': True, 'exception': False, 'allowed': True, 'setupStage': 'complete', 'exceptionKind': 'none'}
        failed = {**base, 'pane': 0, 'ui': 0, 'listing': 0, 'row': 0, 'returned': False, 'exception': True,
                  'allowed': False, 'setupStage': 'dialog', 'exceptionKind': 'missingApi'}
        after = {**base, 'exception': True, 'setupStage': 'pane', 'exceptionKind': 'runtimeOther'}
        processes = ({'exitCode': 0, 'interrupted': False, 'errors': []},
                     {'exitCode': 0, 'interrupted': False, 'errors': ['PRIVATE Steam', 'x']},
                     {'exitCode': 1, 'interrupted': False, 'errors': []},
                     {'exitCode': None, 'interrupted': True, 'errors': []})
        for material in (base, failed, after, None):
            for product in processes:
                for official in processes:
                    with self.subTest(material=material, product=product, official=official):
                        p = {**product, 'rows': [generated, marker]}
                        o = {**official, 'rows': [generated, marker]}
                        m = {**official, 'rows': [material] if material else []}
                        rows = [context.material_gate(m), context.event_gate(p, o)]
                        for row, (pe, oe) in zip(rows, ((p, m), (p, o))):
                            row['diagnostics'] = {'product': context.diagnostic_summary(pe), 'official': context.diagnostic_summary(oe)}
                            row['executionStatus'] = 'interrupted' if pe['interrupted'] or oe['interrupted'] else 'completed'
                            if pe['errors'] or pe['exitCode'] != 0 or pe['interrupted']:
                                row['gatePassed'] = False
                                row['stopReasons'] = sorted({*row['stopReasons'], 'product.observationIncomplete'})
                        safe = context.safe_cases(rows)
                        self.assertEqual([r['gatePassed'] for r in safe], [r['gatePassed'] for r in rows])


class EventExecutionContextTests(unittest.TestCase):
    def product(self):
        return {'rows': [context_row('generated', 1, mainThread=False, pendingWhenFinished=1), context_row('marker', 2)],
                'exitCode': 0, 'interrupted': False, 'errors': []}

    def official(self):
        # Shape of the official quicktest: generation and FinalizeInit inside one asynchronous long event.
        worker = {'mainThread': False, 'programState': 'MapInitializing'}
        return {'rows': [context_row('init', 1, **worker), context_row('generated', 2, **worker, pendingWhenFinished=1),
                         context_row('finalize', 3, 1, **worker, pendingWhenFinished=1),
                         context_row('marker', 4, 1, programState='Playing', currentMap=True)],
                'exitCode': 0, 'interrupted': False, 'errors': []}

    def test_contexts_are_reported_per_phase(self):
        result = context.event_gate(self.product(), self.official())
        self.assertEqual([c['phase'] for c in result['contexts']['official']], ['init', 'generated', 'finalize', 'marker'])
        self.assertEqual(result['contexts']['product'][1],
            {'phase': 'marker', 'mainThread': True, 'programState': 'Entry', 'inLongEvent': True,
             'pendingWhenFinished': 0, 'currentMap': False})

    def test_no_official_pre_finalize_point_in_the_product_context_is_a_stop(self):
        result = context.event_gate(self.product(), self.official())
        self.assertIn('official.noMatchingPreFinalizeContext', result['stopReasons'])
        self.assertFalse(result['gatePassed'])

    def test_matching_pre_finalize_point_adds_no_new_stop_but_cannot_pass_alone(self):
        official = self.official()
        official['rows'][1].update(mainThread=True, programState='Entry')
        result = context.event_gate(self.product(), official)
        self.assertNotIn('official.noMatchingPreFinalizeContext', result['stopReasons'])
        self.assertIn('official.finalizedBeforeMarker', result['stopReasons'])

    def test_rows_without_context_fields_or_unknown_states_are_malformed(self):
        for change in ({'programState': 'PRIVATE'}, {'mainThread': 1}, {'pendingWhenFinished': -1}, {'pendingWhenFinished': True}):
            official = self.official(); official['rows'][1].update(change)
            result = context.event_gate(self.product(), official)
            self.assertIn('official.traceMalformed', result['stopReasons'])
            self.assertNotIn('PRIVATE', json.dumps(result))
        official = self.official(); del official['rows'][1]['currentMap']
        self.assertIn('official.traceMalformed', context.event_gate(self.product(), official)['stopReasons'])

    def test_parser_stops_collecting_after_a_context_marker(self):
        lines = ['[RWMT-CONTEXT] ' + json.dumps(r) for r in self.official()['rows']] + ['2026-10-30 00:00:00.000 ERROR [Verse] later']
        parsed = context.parse_lines(lines, worker=False)
        self.assertEqual(len(parsed['rows']), 4)
        self.assertEqual(parsed['errors'], [])

    def published(self):
        clean = {'exitCode': 0, 'interrupted': False, 'errorCount': 0, 'kinds': []}
        row = context.event_gate(self.product(), self.official())
        row.update(executionStatus='completed', diagnostics={'product': clean, 'official': clean})
        material = {'case': 'material', 'gatePassed': False, 'c0Passed': False, 'stopReasons': ['official.traceMalformed'],
                    'executionStatus': 'completed', 'reachability': {}, 'diagnostics': {'product': clean, 'official': clean}}
        return [material, row]

    def test_public_contexts_are_revalidated_and_bound_to_phases_and_stop(self):
        rows = self.published()
        safe = context.safe_cases(rows)
        self.assertEqual(safe[1]['contexts'], rows[1]['contexts'])
        for mutate in (lambda r: r['contexts']['official'][1].update(programState='PRIVATE'),
                       lambda r: r['contexts']['official'][1].update(extra=1),
                       lambda r: r['contexts']['official'].pop(),
                       lambda r: r['contexts']['official'][0].update(phase='marker'),
                       lambda r: r['stopReasons'].remove('official.noMatchingPreFinalizeContext'),
                       lambda r: r['contexts']['official'][1].update(mainThread=True, programState='Entry')):
            rows = self.published(); mutate(rows[1])
            with self.subTest(rows=rows[1]['contexts']):
                self.assertEqual(context.safe_cases(rows), [])


class MaterialGuiContextTests(unittest.TestCase):
    def row(self, **change):
        row = {'phase': 'material', 'freshGame': True, 'newBill': True, 'pane': 1, 'ui': 1, 'listing': 0, 'row': 0,
               'returned': False, 'exception': True, 'allowed': False, 'setupStage': 'pane',
               'exceptionKind': 'nullReference', 'guiEvent': False, 'windowStack': True}
        row.update(change)
        return {'rows': [row], 'exitCode': 0, 'interrupted': False, 'errors': []}

    def test_missing_gui_event_is_reported_as_its_own_stop(self):
        result = context.material_gate(self.row())
        self.assertIn('official.noGuiEvent', result['stopReasons'])
        self.assertEqual((result['guiEvent'], result['windowStack']), (False, True))
        self.assertNotIn('official.noGuiEvent', context.material_gate(self.row(guiEvent=True))['stopReasons'])

    def test_gui_fields_must_be_booleans_and_come_together(self):
        for change in ({'guiEvent': 1}, {'windowStack': None}):
            self.assertIn('official.traceMalformed', context.material_gate(self.row(**change))['stopReasons'])
        evidence = self.row(); del evidence['rows'][0]['windowStack']
        self.assertIn('official.traceMalformed', context.material_gate(evidence)['stopReasons'])

    def published(self, **change):
        clean = {'exitCode': 0, 'interrupted': False, 'errorCount': 0, 'kinds': []}
        material = context.material_gate(self.row(**change))
        material.update(executionStatus='completed', diagnostics={'product': clean, 'official': clean})
        event = {'case': 'event', 'gatePassed': False, 'c0Passed': False, 'stopReasons': ['official.traceMalformed'],
                 'executionStatus': 'completed', 'phases': {'product': [], 'official': []},
                 'diagnostics': {'product': clean, 'official': clean}}
        return [material, event]

    def test_public_gui_fields_are_bound_to_the_stop(self):
        safe = context.safe_cases(self.published())
        self.assertEqual((safe[0]['guiEvent'], safe[0]['windowStack']), (False, True))
        rows = self.published(); rows[0]['stopReasons'].remove('official.noGuiEvent')
        self.assertEqual(context.safe_cases(rows), [])
        rows = self.published(); rows[0]['guiEvent'] = 'PRIVATE'
        self.assertEqual(context.safe_cases(rows), [])
        rows = self.published(); rows[1]['guiEvent'] = True
        self.assertEqual(context.safe_cases(rows), [])
