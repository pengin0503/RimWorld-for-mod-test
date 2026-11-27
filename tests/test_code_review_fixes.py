"""Regression tests for bugs and hardening improvements found in the full code review."""
from __future__ import annotations

import base64
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile

from tools import (
    codex_workflow,
    knowledge_preflight,
    map_render,
    mod_load_plan,
    private_validation_evidence,
    probe_observations,
    r2_assets,
    signature_diagnostics,
    validation_host as vh,
)


class ControllerHardeningTests(unittest.TestCase):
    def test_level_b_rejects_omitted_or_unknown_outcomes(self):
        request = {
            'levels': ['A', 'B'],
            'tests': [],
            'expectations': {
                'defs': [], 'defValues': [], 'keyed': [],
                'harmonyPatches': [{'owner': 'a', 'targetAssembly': 'Assembly-CSharp', 'targetType': 'T',
                                    'targetMethod': 'M', 'targetParameters': [], 'kind': 'postfix',
                                    'patchType': 'P', 'patchMethod': 'Post'}],
            },
            'allow': {'diagnostics': [], 'translationErrors': []},
            'language': 'English',
            'map': None,
        }
        worker = {
            'executionStatus': 'completed',
            'playDataLoaded': True,
            'activeLanguage': 'English',
            'modOrder': {'matches': True},
            'runningMods': [],
            'diagnosticsSummary': {'dropped': 0},
            'translationErrors': {'count': 0, 'dropped': 0, 'items': []},
            'checks': {
                'defs': [], 'defValues': [], 'keyed': [],
                'harmony': {'available': True, 'expected': []},  # omitted expected patch!
            },
        }
        baseline = {
            'executionStatus': 'completed',
            'playDataLoaded': True,
            'modOrder': {'matches': True},
            'diagnosticsSummary': {'dropped': 0},
            'translationErrors': {'count': 0, 'dropped': 0, 'items': []},
        }
        proc = {'killedFor': None, 'exitCode': 0}
        status, _, reasons, stages, _ = vh.evaluate(
            request, [], worker, None, [], baseline, None, [], proc, 'qualified',
        )
        self.assertEqual(status, 'incomplete')
        self.assertEqual(stages['B']['status'], 'incomplete')
        self.assertIn('harmonyCheckError', [r['code'] for r in reasons])

    def test_level_a_rejects_missing_expectation_results(self):
        request = {
            'levels': ['A'],
            'tests': [],
            'expectations': {
                'defs': [{'type': 'ThingDef', 'defName': 'Steel', 'exists': True}],
                'defValues': [], 'keyed': [], 'harmonyPatches': [],
            },
            'allow': {'diagnostics': [], 'translationErrors': []},
            'language': 'English',
            'map': None,
        }
        worker = {
            'executionStatus': 'completed',
            'playDataLoaded': True,
            'activeLanguage': 'English',
            'modOrder': {'matches': True},
            'runningMods': [],
            'diagnosticsSummary': {'dropped': 0},
            'translationErrors': {'count': 0, 'dropped': 0, 'items': []},
            'checks': {'defs': [], 'defValues': [], 'keyed': []},
        }
        baseline = {
            'executionStatus': 'completed',
            'playDataLoaded': True,
            'modOrder': {'matches': True},
            'diagnosticsSummary': {'dropped': 0},
            'translationErrors': {'count': 0, 'dropped': 0, 'items': []},
        }
        status, _, reasons, stages, _ = vh.evaluate(
            request, [], worker, None, [], baseline, None, [], {'killedFor': None, 'exitCode': 0}, 'qualified',
        )
        self.assertEqual(status, 'incomplete')
        self.assertEqual(stages['A']['status'], 'incomplete')
        self.assertIn('checkError', [r['code'] for r in reasons])

    def test_read_worker_output_handles_non_dict_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / 'events.jsonl').write_text('null\n[1,2]\n{"level":"info","message":"ok"}\n', encoding='utf-8')
            (run_dir / 'worker-result.json').write_text('null', encoding='utf-8')
            result, problem, events = vh.read_worker_output(run_dir, 'r1', 'n1', 0, 100)
            self.assertIsNone(result)
            self.assertEqual(problem, 'workerResultInvalid')
            self.assertEqual(len(events), 3)
            self.assertTrue(all(isinstance(e, dict) for e in events))

    def test_load_snapshot_rejects_corrupt_json_and_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp)
            (snap / 'snapshot.json').write_text('{bad json', encoding='utf-8')
            with self.assertRaises(vh.Blocked) as ctx:
                vh.load_snapshot(snap)
            self.assertEqual(ctx.exception.code, 'snapshotInvalid')

            (snap / 'snapshot.json').write_text(json.dumps({
                'recordType': 'rwmtGameSnapshot', 'schemaVersion': 1,
                'files': {'../escape.txt': {'size': 1, 'sha256': '0' * 64}},
            }), encoding='utf-8')
            with self.assertRaises(vh.Blocked) as ctx:
                vh.load_snapshot(snap)
            self.assertEqual(ctx.exception.code, 'snapshotInvalid')

    def test_extract_mod_archive_rejects_duplicate_dir_and_unsafe_stem(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dup_zip = root / 'dup.zip'
            with zipfile.ZipFile(dup_zip, 'w') as zf:
                zf.writestr('About/', '')
                zf.writestr('About/', '')
                zf.writestr('About/About.xml', '<ModMetaData><packageId>a.b</packageId></ModMetaData>')
            with self.assertRaises(vh.Blocked) as ctx:
                vh.extract_mod_archive(dup_zip, root / 'out1', 1024 * 1024)
            self.assertEqual(ctx.exception.code, 'modInvalid')

            dotdot_zip = root / '...zip'
            with zipfile.ZipFile(dotdot_zip, 'w') as zf:
                zf.writestr('About/About.xml', '<ModMetaData><packageId>a.b</packageId></ModMetaData>')
            dest = root / 'out2'
            extracted = vh.extract_mod_archive(dotdot_zip, dest, 1024 * 1024)
            self.assertTrue(extracted.resolve().is_relative_to(dest.resolve()))


class MapRenderAndLoadPlanTests(unittest.TestCase):
    def _sample_obs(self, *, mod='My.Target', color=None):
        terrain_bytes = struct.pack('<H', 0)
        roof_bytes = b'\x00'
        thing_bytes = struct.pack('<H', 1)
        return {
            'recordType': 'rwmtMapObservation', 'schemaVersion': 1,
            'width': 1, 'height': 1,
            'layers': {
                'terrain': base64.b64encode(terrain_bytes).decode('ascii'),
                'roof': base64.b64encode(roof_bytes).decode('ascii'),
                'thing': base64.b64encode(thing_bytes).decode('ascii'),
            },
            'palettes': {
                'terrain': [{
                    'defName': 'Floor', 'mod': 'ludeon.rimworld', 'cells': 1,
                    'fertility': 0, 'natural': False, 'water': False, 'ice': False,
                    'rock': False, 'soil': False, 'floor': True, 'constructed': True,
                    'color': color or [2.5, -0.5, 1.5, 1.0],
                }],
                'roof': [],
                'thing': [{
                    'defName': 'Widget', 'mod': mod, 'category': 'Building', 'count': 1,
                    'naturalRock': False, 'resourceRock': False, 'tree': False,
                    'chunk': False, 'humanlike': False, 'animal': False,
                }],
            },
            'things': [{'def': 1, 'x': 0, 'z': 0, 'rect': [0, 0, 0, 0], 'rotation': 0, 'playerFaction': True}],
            'genSteps': [{'defName': 'Step', 'mod': mod}],
        }

    def test_map_render_case_insensitive_targets_and_hdr_color_clamping(self):
        obs = self._sample_obs(mod='My.Target', color=[3.0, -1.0, 2.0, 1.0])
        png_bytes, legend = map_render.render(obs, ['my.target'], scale=1)
        self.assertTrue(png_bytes.startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertTrue(any(row['key'] == 'targetThing' for row in legend))
        summary = map_render.summarize(obs, ['my.target'])
        self.assertEqual(len(summary['targetThings']), 1)
        self.assertEqual(len(summary['genStepsFromTargets']), 1)

    def test_map_render_rejects_zero_size_and_oob_palette(self):
        obs = self._sample_obs()
        obs['width'] = 0
        with self.assertRaises(map_render.ObservationError):
            map_render.decode(obs)

        obs2 = self._sample_obs()
        obs2['layers']['terrain'] = base64.b64encode(struct.pack('<H', 99)).decode('ascii')
        with self.assertRaises(map_render.ObservationError):
            map_render.decode(obs2)

    def test_mod_load_plan_select_asset_resolved_language_and_continue(self):
        self.assertTrue(mod_load_plan.select_asset(
            'Languages/Japanese/Keyed/a.xml', [''], language='Japanese (日本語)',
        ))
        self.assertTrue(mod_load_plan.select_asset(
            '1.7/Languages/Japanese/Keyed/a.xml', ['', '1.7'], language='Japanese (日本語)',
        ))


class AuxiliaryToolsHardeningTests(unittest.TestCase):
    def test_cow_evidence_rejects_null_mode_without_type_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            rows = [{'repeat': i // 2 + 1, 'mode': None if i == 0 else ('copy' if i % 2 == 0 else 'reflink')}
                    for i in range(10)]
            (out / 'summary.json').write_text(json.dumps({'rows': rows}), encoding='utf-8')
            result = private_validation_evidence.inspect('cow', out)
            self.assertFalse(result['complete'])
            self.assertFalse(result['accepted'])

    def test_ensure_safe_destination_blocks_traversal_and_allows_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(r2_assets.ensure_safe_destination(root, ''), root)
            for bad in ('../outside', 'a/../../outside', '/etc/passwd', 'a\\b'):
                with self.assertRaises(r2_assets.AssetError):
                    r2_assets.ensure_safe_destination(root, bad)

    def test_knowledge_preflight_active_validation_and_case_insensitive_about(self):
        db = knowledge_preflight.load_database()
        with tempfile.TemporaryDirectory() as tmp:
            mod = Path(tmp) / 'mymod'
            (mod / 'About').mkdir(parents=True)
            (mod / 'About' / 'about.xml').write_text(
                '<ModMetaData><packageId>author.mymod</packageId><supportedVersions><li>1.7</li></supportedVersions></ModMetaData>',
                encoding='utf-8',
            )
            bad_report = knowledge_preflight.inspect_mod(mod, db, active_packages=['bad id with spaces'])
            bad_codes = [i['code'] for i in bad_report['issues']]
            self.assertIn('unsafeInput', bad_codes)
            self.assertNotIn('invalidMetadata', bad_codes)
            report = knowledge_preflight.inspect_mod(mod, db)
            codes = [i['code'] for i in report['issues']]
            self.assertNotIn('missingAbout', codes)

    def test_probe_observations_handles_deep_json_recursion(self):
        deep = '[' * 2000 + ']' * 2000
        result = probe_observations.evaluate_events([deep], [{'tick': 1, 'id': 'probe.counter', 'equals': 1}])
        self.assertEqual(result['status'], 'incomplete')
        self.assertTrue(result['invalidEvidence'])

    def test_signature_diagnostics_sets_truncated_on_overload_cap(self):
        overloads = [{'token': 0x06000001 + i, 'return': {'kind': 'primitive', 'name': 'Void'}, 'parameters': []}
                     for i in range(17)]
        res = signature_diagnostics.unsupported_positions(overloads, set())
        self.assertTrue(res['truncated'])

    def test_codex_workflow_by_package_avoids_name_collision_ambiguity(self):
        index = {
            'schema_version': 1,
            'mods': [
                'not-a-dict',
                {'workshop_id': '12345', 'package_id': 'dep.mod', 'name': 'Dep Mod'},
                {'workshop_id': '99999', 'package_id': 'other.mod', 'name': '12345'},
            ],
        }
        import xml.etree.ElementTree as ET
        meta = ET.fromstring('<ModMetaData><packageId>dep.mod</packageId></ModMetaData>')
        order = codex_workflow.resolve_mod_graph(index, ['dep.mod'], lambda _m: meta)
        self.assertEqual([m['workshopId'] for m in order], ['12345'])


if __name__ == '__main__':
    unittest.main()
