import json
import unittest
from tools import private_static_audit as audit


class SignatureDiagnosticTests(unittest.TestCase):
    def item(self):
        return {'token': 0x06000001, 'return': {'kind': 'primitive', 'name': 'Void'},
                'parameters': [], 'genericCount': 0, 'static': True,
                'visibility': 'Public', 'calls': [], 'branches': [], 'exceptions': []}

    def summary(self, item, bound=True):
        identity = {'runId': '100-1', 'commit': 'a'*40}
        raw = {**identity, 'verified': True, 'types': [{'id': 'game', 'found': True,
            'methods': [{'name': 'InitNewGame', 'overloads': [item]},
                        {'name': 'FinalizeInit', 'overloads': []}]}]}
        if not bound:
            raw['commit'] = 'b'*40
        return audit.public_summary(raw, identity)

    def test_positions_have_only_validated_metadata_and_no_private_names(self):
        item = self.item()
        meta = {'handle': 'definition', 'scope': 'module', 'depth': 1}
        item['return'] = {'kind': 'named', 'name': 'PRIVATE.Return', 'metadata': meta}
        item['parameters'] = [{'kind': 'generic', 'element': {'kind': 'named', 'name': 'System.Action`1'},
                               'arguments': [{'kind': 'named', 'name': 'PRIVATE.Argument'}]}]
        method = self.summary(item)['types'][0]['methods'][0]
        self.assertEqual(method['unsupportedTypes'], {'items': [
            {'token': 0x06000001, 'site': 'return', 'path': [], 'metadata': meta},
            {'token': 0x06000001, 'site': 'parameter', 'index': 0, 'path': [0]}], 'truncated': False})
        self.assertNotIn('PRIVATE', json.dumps(method))

    def test_metadata_does_not_weaken_known_type_validation(self):
        meta = {'handle': 'reference', 'scope': 'assembly', 'depth': 0}
        node = {'kind': 'named', 'name': 'System.Action', 'metadata': meta}
        self.assertEqual(audit.normalized_type(node), 'System.Action')
        for bad in ({**meta, 'scope': 'PRIVATE'}, {**meta, 'depth': True}, {**meta, 'extra': 'PRIVATE'}):
            with self.assertRaises(ValueError):
                audit.normalized_type({**node, 'metadata': bad})

    def test_unbound_evidence_cannot_publish_diagnostics(self):
        item = self.item(); item['return'] = {'kind': 'named', 'name': 'PRIVATE'}
        self.assertEqual(self.summary(item, bound=False)['types'], [])

    def test_diagnostic_work_and_output_are_bounded(self):
        item = self.item()
        item['parameters'] = [{'kind': 'generic', 'element': {'kind': 'named', 'name': 'PRIVATE'},
                               'arguments': [{'kind': 'named', 'name': 'PRIVATE'} for _ in range(32)]} for _ in range(64)]
        result = self.summary(item)['types'][0]['methods'][0]['unsupportedTypes']
        self.assertLessEqual(len(result['items']), 128)
        self.assertTrue(result['truncated'])
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_invalid_metadata_and_token_are_never_echoed(self):
        item = self.item(); item['return'] = {'kind': 'named', 'name': 'PRIVATE', 'metadata': {'scope': 'PRIVATE'}}
        result = self.summary(item)['types'][0]['methods'][0]['unsupportedTypes']
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertNotIn('metadata', result['items'][0])
        item['token'] = False
        self.assertEqual(self.summary(item)['types'][0]['methods'][0]['unsupportedTypes']['items'], [])

    def test_fixed_hypotheses_report_ids_without_adopting_atoms(self):
        for name, ident in [('System.Collections.IEnumerator', 'ienumerator'),
                            ('Verse.ThingFilterUI+UIState', 'filter-ui-state')]:
            item = self.item(); item['return'] = {'kind': 'named', 'name': name}
            row = self.summary(item)['types'][0]['methods'][0]['unsupportedTypes']['items'][0]
            self.assertEqual(row.get('candidate'), ident)
            with self.assertRaises(ValueError):
                audit.normalized_type(item['return'])
