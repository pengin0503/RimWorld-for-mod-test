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

    def test_summary_does_not_publish_private_strings(self):
        m=self.helper();bad=self.evidence()
        bad['errors']=['PRIVATE log'];bad['rows'][2]['view']['x']='PRIVATE path'
        result=m.compare(bad,self.evidence(),600)
        self.assertNotIn('PRIVATE',str(result))

if __name__ == '__main__': unittest.main()
