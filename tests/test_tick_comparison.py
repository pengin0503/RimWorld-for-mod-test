"""A second empty run, shifted tick or partial evidence cannot qualify D."""
import copy
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'experiments/official-comparison/compare_ticks.py'

class TickComparisonTests(unittest.TestCase):
    def helper(self):
        self.assertTrue(SCRIPT.is_file(), 'independent tick comparison is missing')
        spec = importlib.util.spec_from_file_location('tick_compare', SCRIPT)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        return m

    def evidence(self):
        view={'width':1280,'height':720,'rootSize':24,'x':125,'z':125,'zoom':'Middle'}
        setup={'seed':'rwmt','sizeX':250,'sizeZ':250,'biome':'AridShrubland',
               'tile':85560,'generator':'Base_Player','mods':['ludeon.rimworld','rwmodtest.tickprobe']}
        rows=[{'kind':'started','gameTick':0,'counter':0}]
        for n in (0,60,600):
            rows.append({'kind':'point','relative':n,'gameTick':n,'counter':n,'startedCalls':1,
                         'longEvent':False,'view':view.copy(),'setup':copy.deepcopy(setup)})
        rows.append({'kind':'end','advanced':600,'gameTick':600,'counter':600})
        return {'rows':rows,'errors':[],'exitCode':0,'interrupted':False}

    def test_matching_independent_rows_establish_only_the_requested_boundary(self):
        m=self.helper(); a=self.evidence()
        self.assertTrue(m.compare(a, copy.deepcopy(a), 600)['equivalent'])

    def test_empty_or_partial_or_duplicate_rows_cannot_qualify(self):
        m=self.helper()
        for rows in ([], self.evidence()['rows'][:-1], self.evidence()['rows']+[self.evidence()['rows'][2]]):
            bad=self.evidence();bad['rows']=rows
            self.assertFalse(m.compare(bad,self.evidence(),600)['equivalent'])

    def test_counter_tick_initialization_and_view_differences_are_detected(self):
        m=self.helper()
        for field,value in [('gameTick',601),('counter',599),('longEvent',True),('startedCalls',2),('relative',601)]:
            bad=self.evidence();bad['rows'][3][field]=value
            self.assertFalse(m.compare(bad,self.evidence(),600)['equivalent'],field)
        for change in ('view','setup'):
            bad=self.evidence();bad['rows'][3][change]['unexpected']='different'
            self.assertFalse(m.compare(bad,self.evidence(),600)['equivalent'],change)

    def test_matching_errors_or_interrupted_results_do_not_qualify(self):
        m=self.helper()
        for field,value in [('errors',['same error']),('exitCode',1),('interrupted',True)]:
            a=self.evidence();a[field]=value
            self.assertFalse(m.compare(a,copy.deepcopy(a),600)['equivalent'])

    def test_identical_malformed_contexts_and_reordered_rows_do_not_qualify(self):
        m=self.helper()
        for section,key,value in [('view','width',0),('view','x',True),('setup','mods',[]),('setup','seed','other')]:
            a=self.evidence()
            for row in a['rows']:
                if row.get('kind') == 'point': row[section][key]=value
            self.assertFalse(m.compare(a,copy.deepcopy(a),600)['equivalent'], (section,key))
        a=self.evidence();a['rows'][0],a['rows'][1]=a['rows'][1],a['rows'][0]
        self.assertFalse(m.compare(a,copy.deepcopy(a),600)['equivalent'])
        self.assertFalse(m.compare(self.evidence(),self.evidence(),True)['equivalent'])

    def test_complete_summary_requires_all_three_planned_runs(self):
        m=self.helper()
        self.assertTrue(callable(getattr(m, 'summary_complete', None)), 'summary completion guard missing')
        rows=[{'count':60,'equivalent':True,'sensitivity':True},
              {'count':600,'equivalent':True,'sensitivity':True},
              {'count':600,'equivalent':True,'sensitivity':True}]
        self.assertFalse(m.summary_complete(rows[:1]))
        self.assertFalse(m.summary_complete(rows[:2]))
        self.assertTrue(m.summary_complete(rows))
        rows[2]['sensitivity']=False
        self.assertFalse(m.summary_complete(rows))

    def test_official_errors_mentioning_known_noise_are_not_discarded(self):
        m=self.helper()
        for message in ('Unhandled exception in NativeAllocationRuntime during frame update',
                        'Persistent allocation failed during tick',
                        'Unexpected [Steamworks.NET] SteamAPI.Init() failed in tick'):
            result=m.parse_lines(['2026-10-29 00:00:00.000 ERROR [Verse] '+message])
            self.assertEqual(len(result['errors']),1,message)

    def test_full_public_summary_cannot_expose_private_identifiers(self):
        m=self.helper()
        self.assertTrue(callable(getattr(m,'summarize_run',None)), 'fixed summary builder missing')
        bad=self.evidence();bad['errors']=['PrivateTenant.CustomerException at PrivateTenant.SecretMethod()']
        result=m.summarize_run(bad,self.evidence(),600,seconds=1.0,product_d='completed')
        self.assertNotIn('PrivateTenant',str(result))
        self.assertFalse(result['equivalent'])

    def test_summary_does_not_publish_private_strings(self):
        m=self.helper();bad=self.evidence()
        bad['errors']=['PRIVATE log'];bad['rows'][2]['view']['x']='PRIVATE path'
        result=m.compare(bad,self.evidence(),600)
        self.assertNotIn('PRIVATE',str(result))

if __name__ == '__main__': unittest.main()
