"""Synthetic checks for the development-only rendered bill dialog research (no game files)."""
import copy
import importlib.util
from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('probe_c_rendered', REPO/'experiments/official-comparison/probe_c_rendered.py')
rendered = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rendered)

RENDER_NOISE = ['[Steamworks.NET] SteamAPI.Init() failed. Possible causes: Steam client not running',
                'GLFW Error (PlatformUnavailable): Wayland: Platform not initialized',
                "Used UnityData before it's initialized.",
                'GpuProbe: incomplete after 5774 ms (0 GFLOP/s, 0.0 GB/s), using conservative (low) tier']


def product_rows():
    return [{'expected': {'recipe': r, 'thing': t, 'visible': v, 'allowed': a},
             'actual': {'visible': v, 'allowed': a}, 'outcome': 'match'} for r, t, v, a in rendered.ROWS]


def case(recipe, listed, allowed):
    return {'recipe': recipe, 'setup': 'open', 'opened': True, 'openedOnMainThread': True, 'openEventType': 7,
            'otherDialogsBeforeOpen': 1, 'repaintsWhileOpen': 30, 'freshGameKept': True, 'removed': True,
            'contents': {'7': 30, '8': 30}, 'pane': {'7': 30, '8': 30}, 'ui': 60, 'listing': 60,
            'paneRepaints': 30, 'rowCount': len(listed), 'exception': False, 'exceptionKind': 'none',
            'listed': {t: ([7, 8] if t in listed else []) for t in rendered.THINGS}, 'allowed': allowed}


def observer():
    trace = {'phase': 'rendered', 'stop': 'none', 'totalRepaints': 96, 'drainRepaints': 5, 'lateContents': 2, 'cases': [
        case('RWMT_BillOptions', {'RWMT_BillGrain', 'RawCorn'}, {'RWMT_BillGrain': True, 'RawCorn': False, 'RawPotatoes': False}),
        case('RWMT_BillHidden', {'RawCorn'}, {'RWMT_BillGrain': True, 'RawCorn': False, 'RawPotatoes': False})]}
    return {'rows': [trace], 'errors': list(RENDER_NOISE), 'exitCode': 0, 'interrupted': False, 'seconds': 42.0}


def control():
    return {'rows': [{'phase': 'rendered', 'stop': 'none', 'totalRepaints': 35, 'drainRepaints': 5, 'lateContents': 0,
                      'cases': []}], 'errors': list(RENDER_NOISE), 'exitCode': 0, 'interrupted': False, 'seconds': 30.0}


def product():
    return {'executionStatus': 'completed', 'status': 'incomplete', 'stages': {'C': {'status': 'completed'}},
            'reasons': [{'code': 'experimental'}, {'code': 'cNotQualified'}], 'checks': {'billIngredients': product_rows()}}


class RenderedComparisonTests(unittest.TestCase):
    def evaluate(self, prod=None, ctrl=None, obs=None):
        prod, ctrl, obs = prod or product(), ctrl or control(), obs or observer()
        rows = rendered.compare(prod['checks']['billIngredients'], obs)
        return rows, rendered.gate(prod, ctrl, obs, rows)

    def test_matching_rows_agree_but_never_qualify(self):
        rows, result = self.evaluate()
        self.assertTrue(result['agreement'], result)
        self.assertIs(result['qualified'], False)
        self.assertTrue(all(r['visibleAgrees'] and r['allowedAgrees'] for r in rows))

    def test_product_visible_without_dialog_row_disagrees(self):
        prod = product()
        prod['checks']['billIngredients'][0]['actual']['visible'] = True  # hidden-filter fault reported as visible
        rows, result = self.evaluate(prod=prod)
        self.assertFalse(rows[0]['visibleAgrees'])
        self.assertFalse(result['checks']['rowsAgree'])
        self.assertFalse(result['agreement'])

    def test_dialog_row_missing_for_visible_product_answer_disagrees(self):
        obs = observer()
        obs['rows'][0]['cases'][0]['listed']['RawCorn'] = []
        rows, result = self.evaluate(obs=obs)
        self.assertFalse(next(r for r in rows if r['thing'] == 'RawCorn')['visibleAgrees'])
        self.assertFalse(result['agreement'])

    def test_allowed_mismatch_disagrees(self):
        obs = observer()
        obs['rows'][0]['cases'][0]['allowed']['RawCorn'] = True
        _, result = self.evaluate(obs=obs)
        self.assertFalse(result['checks']['rowsAgree'])

    def test_listing_in_only_one_event_kind_is_inconsistent(self):
        obs = observer()
        obs['rows'][0]['cases'][0]['listed']['RawCorn'] = [8]
        rows, result = self.evaluate(obs=obs)
        row = next(r for r in rows if r['thing'] == 'RawCorn')
        self.assertFalse(row['officialListingConsistent'])
        self.assertFalse(row['visibleAgrees'])
        self.assertFalse(result['agreement'])

    def test_undrawn_or_disturbed_dialog_is_not_an_observation(self):
        for key, value in (('exception', True), ('freshGameKept', False), ('removed', False), ('paneRepaints', 2),
                           ('openedOnMainThread', False), ('ui', 59)):
            obs = observer()
            for c in obs['rows'][0]['cases']:
                c[key] = value
                if key == 'paneRepaints': c['pane'] = {'7': 2, '8': 2}; c['ui'] = c['listing'] = 4
            rows, result = self.evaluate(obs=obs)
            self.assertFalse(any(r['officialObserved'] for r in rows), key)
            self.assertFalse(result['checks']['dialogsDrawn'], key)
            self.assertFalse(result['agreement'], key)

    def test_missing_or_duplicate_case_is_not_observed(self):
        obs = observer(); del obs['rows'][0]['cases'][1]
        rows, result = self.evaluate(obs=obs)
        self.assertFalse(rows[0]['officialObserved'])
        self.assertFalse(result['agreement'])
        obs = observer(); obs['rows'][0]['cases'].append(copy.deepcopy(obs['rows'][0]['cases'][0]))
        rows, result = self.evaluate(obs=obs)
        self.assertFalse(rows[1]['officialObserved'])
        self.assertFalse(result['agreement'])

    def test_diagnostics_must_equal_the_no_dialog_control(self):
        obs = observer(); obs['errors'].append('Exception filling window for RimWorld.Dialog_BillConfig: System.NullReferenceException')
        _, result = self.evaluate(obs=obs)
        self.assertFalse(result['checks']['diagnosticsMatchControl'])
        obs = observer(); obs['errors'].append('Something unknown broke')
        _, result = self.evaluate(obs=obs)
        self.assertFalse(result['checks']['diagnosticsMatchControl'])
        ctrl = control(); ctrl['errors'] = ctrl['errors'][:-1]
        _, result = self.evaluate(ctrl=ctrl)
        self.assertFalse(result['checks']['diagnosticsMatchControl'])

    def test_official_runs_must_complete_and_control_must_stay_idle(self):
        for mutate in (lambda o: o.update(exitCode=1), lambda o: o.update(interrupted=True),
                       lambda o: o.update(rows=[]), lambda o: o['rows'][0].update(stop='frameLimit')):
            for which in ('ctrl', 'obs'):
                ctrl, obs = control(), observer()
                mutate(ctrl if which == 'ctrl' else obs)
                _, result = self.evaluate(ctrl=ctrl, obs=obs)
                self.assertFalse(result['checks']['officialCompleted'], which)
                self.assertFalse(result['agreement'], which)
        ctrl = control(); ctrl['rows'][0]['cases'] = [case('RWMT_BillOptions', set(), {})]
        _, result = self.evaluate(ctrl=ctrl)
        self.assertFalse(result['checks']['controlOpenedNothing'])

    def test_product_must_complete_with_only_known_unqualified_reasons(self):
        for mutate in (lambda p: p.update(executionStatus='interrupted'), lambda p: p['stages']['C'].update(status='blocked'),
                       lambda p: p['reasons'].append({'code': 'newErrors'})):
            prod = product(); mutate(prod)
            _, result = self.evaluate(prod=prod)
            self.assertFalse(result['checks']['productCompleted'])
            self.assertFalse(result['agreement'])

    def test_missing_product_observation_never_agrees(self):
        prod = product(); prod['checks']['billIngredients'] = prod['checks']['billIngredients'][1:]
        rows, result = self.evaluate(prod=prod)
        self.assertIsNone(rows[0]['productVisible'])
        self.assertFalse(rows[0]['visibleAgrees'])
        self.assertFalse(result['agreement'])

    def test_classify_and_config(self):
        counts = rendered.classify([*RENDER_NOISE, 'Exception filling window for RimWorld.Dialog_BillConfig: x', 'other text', None])
        self.assertEqual(counts, {'steamInit': 1, 'glfwWaylandUnavailable': 1, 'unityDataBeforeInit': 1,
                                  'gpuProbeIncomplete': 1, 'billDialogWindowException': 1, 'other': 2})
        xml = rendered.config(True)
        self.assertIn('<official>true</official>', xml)
        self.assertIn('<li>RWMT_BillHidden</li>', xml)
        self.assertIn('<recipes></recipes>', rendered.config(False, ()))
        for bad in ((1,), ('a b',), ('x' * 65,), ('<li>',)):
            with self.assertRaises(ValueError):
                rendered.config(True, bad)
        with self.assertRaises(ValueError):
            rendered.config('true')

    def test_private_paths_are_rejected(self):
        with self.assertRaises(ValueError):
            rendered.launch_official(REPO, 77, None)
        with self.assertRaises(SystemExit):
            rendered.main(['--snapshot', '/nonexistent', '--out', str(REPO/'private-out'), '--harmony-dll', '/nonexistent'])


FLOUR = rendered.load_spec({'name': 'flour', 'expand': True, 'allowProductMismatch': True, 'rows': [
    {'recipe': 'VCE_CookBakeSimple', 'thing': 'VCE_Flour', 'visible': True, 'allowed': True},
    {'recipe': 'VCE_CookBakeSimple', 'thing': 'Hay', 'visible': False, 'allowed': False}]})


def expanded_case(listed, initially=(), allowed=None):
    c = case('VCE_CookBakeSimple', listed, allowed or {'VCE_Flour': True, 'Hay': False})
    c['listed'] = {t: ([7, 8] if t in listed else []) for t in FLOUR['things']}
    c.update(expanded=True, restored=True, openedCategories=['PlantMatter', 'ResourcesRaw'], categories=['PlantMatter'])
    c['initial'] = {'pane': {'7': 4, '8': 4}, 'ui': 8, 'listing': 8, 'paneRepaints': 4, 'rowCount': len(initially),
                    'listed': {t: ([7, 8] if t in initially else []) for t in FLOUR['things']}, 'categories': []}
    return c


def flour_observer(c=None):
    obs = observer()
    obs['rows'][0].update(expand=True, cases=[c or expanded_case({'VCE_Flour'})])
    return obs


def flour_product(visible=True, mismatch=False):
    prod = product()
    prod['checks']['billIngredients'] = [
        {'expected': {'recipe': r, 'thing': t, 'visible': v, 'allowed': a},
         'actual': {'visible': (visible if t == 'VCE_Flour' else v), 'allowed': a},
         'outcome': 'mismatch' if (mismatch and t == 'VCE_Flour') else 'match'} for r, t, v, a in FLOUR['rows']]
    if mismatch:
        prod['stages']['C']['status'] = 'failed'
        prod['reasons'].append({'code': 'billIngredientMismatch'})
    return prod


class RealModSpecTests(unittest.TestCase):
    def evaluate(self, prod, obs, spec=FLOUR, ctrl=None):
        rows = rendered.compare(prod['checks']['billIngredients'], obs, spec)
        return rows, rendered.gate(prod, ctrl or control(), obs, rows, spec)

    def test_expanded_listing_is_compared_and_default_state_only_recorded(self):
        rows, result = self.evaluate(flour_product(), flour_observer())
        self.assertTrue(result['agreement'], result)
        self.assertIs(result['qualified'], False)
        flour = next(r for r in rows if r['thing'] == 'VCE_Flour')
        self.assertIs(flour['officialListedOnRepaint'], True)
        self.assertIs(flour['officialListedInitially'], False)

    def test_buggy_version_agrees_when_both_sides_hide_the_flour(self):
        obs = flour_observer(expanded_case(set()))
        rows, result = self.evaluate(flour_product(visible=False, mismatch=True), obs)
        self.assertTrue(result['agreement'], result)
        self.assertIs(next(r for r in rows if r['thing'] == 'VCE_Flour')['productOutcome'], 'mismatch')

    def test_product_and_dialog_disagree_in_either_direction(self):
        for prod_visible, listed in ((True, set()), (False, {'VCE_Flour'})):
            _, result = self.evaluate(flour_product(visible=prod_visible, mismatch=not prod_visible),
                                      flour_observer(expanded_case(listed)))
            self.assertFalse(result['checks']['rowsAgree'])
            self.assertFalse(result['agreement'])

    def test_mismatch_reason_only_when_the_spec_allows_it(self):
        _, result = self.evaluate(flour_product(visible=False, mismatch=True), flour_observer(expanded_case(set())),
                                  spec=dict(FLOUR, allowProductMismatch=False))
        self.assertFalse(result['checks']['productCompleted'])
        prod = flour_product(visible=False, mismatch=True); prod['reasons'].append({'code': 'newErrors'})
        _, result = self.evaluate(prod, flour_observer(expanded_case(set())))
        self.assertFalse(result['checks']['productCompleted'])
        prod = flour_product(); prod['stages']['C']['status'] = 'failed'
        _, result = self.evaluate(prod, flour_observer())
        self.assertFalse(result['checks']['productCompleted'])
        prod = flour_product(); prod['reasons'].append({'code': 'billIngredientMismatch'})
        _, result = self.evaluate(prod, flour_observer(), spec=dict(FLOUR, allowProductMismatch=False))
        self.assertFalse(result['checks']['productCompleted'])

    def test_expansion_must_happen_and_be_undone(self):
        for mutate in (lambda c: c.update(expanded=False), lambda c: c.update(restored=False),
                       lambda c: c.update(initial=None), lambda c: c['initial'].update(paneRepaints=1),
                       lambda c: c.pop('openedCategories')):
            c = expanded_case({'VCE_Flour'}); mutate(c)
            rows, result = self.evaluate(flour_product(), flour_observer(c))
            self.assertFalse(result['checks']['dialogsDrawn'])
            self.assertFalse(any(r['officialObserved'] for r in rows))
        obs = flour_observer(); obs['rows'][0]['expand'] = False
        _, result = self.evaluate(flour_product(), obs)
        self.assertFalse(result['checks']['dialogsDrawn'])
        # An expanded trace is not an observation for a default-state spec either.
        _, result = self.evaluate(flour_product(), flour_observer(), spec=dict(FLOUR, expand=False))
        self.assertFalse(result['checks']['dialogsDrawn'])

    def test_other_diagnostics_must_be_identical_to_the_control(self):
        obs, ctrl = flour_observer(), control()
        for run in (obs, ctrl):
            run['errors'].append('[VEF] some MOD warning')
        _, result = self.evaluate(flour_product(), obs, ctrl=ctrl)
        self.assertTrue(result['checks']['diagnosticsMatchControl'])
        ctrl['errors'][-1] = '[VEF] another MOD warning'
        _, result = self.evaluate(flour_product(), obs, ctrl=ctrl)
        self.assertFalse(result['checks']['diagnosticsMatchControl'])

    def test_spec_validation(self):
        good = {'recipe': 'R', 'thing': 'T', 'visible': True, 'allowed': False}
        for bad in ({}, {'rows': []}, {'rows': [dict(good, visible=1)]}, {'rows': [dict(good, recipe='a b')]},
                    {'rows': [good, good]}, {'rows': [good], 'expand': 'yes'}, {'rows': [good], 'extra': 1},
                    {'rows': [dict(good, note='x')]}, {'name': 'a/b', 'rows': [good]}):
            with self.assertRaises(ValueError):
                rendered.load_spec(bad)
        spec = rendered.load_spec({'rows': [good, dict(good, thing='U'), dict(good, recipe='Q')]})
        self.assertEqual(spec['recipes'], ('R', 'Q'))
        self.assertEqual(spec['things'], ('T', 'U'))
        self.assertEqual(rendered.FIXTURE_SPEC['rows'], rendered.ROWS)
        self.assertIn('<expand>true</expand><openMask>4</openMask>', rendered.config(True, ('R',), ('T',), True))

    def test_real_request_puts_the_observer_after_harmony(self):
        base = {'official': ['Core'], 'language': 'English', 'mods': [
            {'path': '/p/h', 'packageId': 'brrainz.harmony', 'target': False},
            {'path': '/p/v', 'packageId': 'OskarPotocki.VanillaFactionsExpanded.Core', 'target': False},
            {'path': '/p/f', 'packageId': 'pengin0503.vce.flouralternatives', 'target': True}]}
        observer = Path('/p/o')  # str() is platform-specific (backslashes on Windows)
        request = rendered.real_request(base, observer, FLOUR)
        self.assertEqual([m['path'] for m in request['mods']], ['/p/h', str(observer), '/p/v', '/p/f'])
        self.assertEqual(request['mods'][1], {'path': str(observer), 'target': False})
        self.assertEqual(request['levels'], ['A', 'C'])
        self.assertEqual(len(request['expectations']['billIngredients']), 2)
        self.assertEqual(request['official'], ['Core'])
        for broken in ({'mods': base['mods'][1:]}, {'mods': [dict(m, target=False) for m in base['mods']]},
                       {'mods': base['mods'] + [{'path': '/x', 'packageId': 'rwmodtest.crendered'}]}, {}):
            with self.assertRaises(ValueError):
                rendered.real_request(broken, Path('/p/o'), FLOUR)
        about = rendered.observer_about('brrainz.harmony')
        self.assertIn('<loadAfter><li>brrainz.harmony</li></loadAfter>', about)
        with self.assertRaises(ValueError):
            rendered.observer_about('someone.else')


if __name__ == '__main__':
    unittest.main()
