"""Fixed helper protocols; no exit-code-only success or arbitrary identifier output."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from tools import private_validation as pv
from tools import private_validation_evidence as evidence


class EvidenceTests(unittest.TestCase):
    def test_smoke_requires_exact_cases_and_qualified_game_results(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d); rows=[dict(case=n,ok=True,status='passed',executionStatus='completed',fidelity='qualified')
                              for n in ('ok','harmony-ok','map-ok')]
            pv.write_json(out/'matrix.json',rows)
            self.assertEqual(evidence.inspect('smoke',out),{'complete':True,'accepted':True,'qualified':True,'failed':False})
            rows[-1]['status']='incomplete'; rows[-1]['fidelity']='experimental'
            pv.write_json(out/'matrix.json',rows)
            self.assertFalse(evidence.inspect('smoke',out)['qualified'])
            pv.write_json(out/'matrix.json',rows[:-1])
            self.assertFalse(evidence.inspect('smoke',out)['complete'])

    def test_d_partial_or_foreign_cases_cannot_confirm_acceptance(self):
        names=['ticks-60','ticks-600','ticks-600-reuse','wrong-value','unknown-id','missing-probe',
               'throwing-probe','timeout','memory-limit','log-limit']
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            rows=[dict(case=n,ok=True,status='incomplete',D='completed' if n.startswith('ticks') else
                       'failed' if n=='wrong-value' else 'incomplete') for n in names]
            pv.write_json(out/'safe-summary.json',{'runs':rows,'ok':True})
            self.assertTrue(evidence.inspect('d-regression',out)['accepted'])
            rows[-1]['case']='PRIVATE'
            pv.write_json(out/'safe-summary.json',{'runs':rows,'ok':True})
            self.assertFalse(evidence.inspect('d-regression',out)['complete'])

    def test_comparison_mismatch_is_complete_but_not_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d); rows=[dict(count=n,equivalent=False,sensitivity=True,productD='completed') for n in (60,600,600)]
            pv.write_json(out/'safe-summary.json',{'runs':rows,'ok':False})
            self.assertEqual(evidence.inspect('d-compare',out),{'complete':True,'accepted':False,'qualified':False,'failed':False})

    def test_cow_rejects_boolean_repeats_and_nonfinite_timings(self):
        rows=[dict(repeat=n,mode=m,seconds=.1,independent=True,modes={m:1032},additionalDataBytes=0 if m=='reflink' else 302_000_000)
              for n in range(1,6) for m in ('copy','reflink')]
        data=dict(ok=True,filesystem='dedicated-btrfs',files=516,sourceDataBytes=150_994_944,rows=rows,
                  crossDeviceFallback=True,staleHashesRejected=True,warmCache=True,metadataIncluded=False)
        with tempfile.TemporaryDirectory() as d:
            out=Path(d); pv.write_json(out/'summary.json',data)
            self.assertTrue(evidence.inspect('cow',out)['accepted'])
            data['rows'][0]['repeat']=True
            pv.write_json(out/'summary.json',data)
            self.assertFalse(evidence.inspect('cow',out)['accepted'])
            data['rows'][0]['repeat']=1; data['rows'][0]['seconds']=float('nan')
            (out/'summary.json').write_text(json.dumps(data))
            self.assertFalse(evidence.inspect('cow',out)['accepted'])

    def test_event_records_a_machine_readable_checkpoint(self):
        path=Path(__file__).parent/'integration/run_event_choice.py'
        spec=importlib.util.spec_from_file_location('event_private',path)
        helper=importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
        with tempfile.TemporaryDirectory() as d:
            out=Path(d); rows=[]
            helper.record_result(out,rows,'positive',True,{'status':'incomplete','stages':{'C':{'status':'completed'}}})
            self.assertEqual(json.loads((out/'summary.json').read_text()),
                             [{'case':'positive','ok':True,'status':'incomplete','stage':'completed'}])
