"""Read fixed private helper protocols. Do not copy diagnostics or arbitrary names."""
import json
import math
from pathlib import Path

SMOKE = ('ok', 'harmony-ok', 'map-ok')
MATERIALS = ('positive','hidden-fault','fixed-pane','outside-tree','missing-thing','missing-def')
EVENTS = ('positive','wrong-count','wrong-item','missing-fixture')
TICKS = ('ticks-60','ticks-600','ticks-600-reuse','wrong-value','unknown-id','missing-probe',
         'throwing-probe','timeout','memory-limit','log-limit')


def read(path):
    try:
        if path.stat().st_size > 4*1024*1024: return {}
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError): return {}


def fixed_rows(rows, names):
    return (isinstance(rows,list) and [r.get('case') if isinstance(r,dict) else None for r in rows] == list(names)
            and all(type(r.get('ok')) is bool for r in rows))


def inspect(kind, out):
    result = {'complete':False, 'accepted':False, 'qualified':False, 'failed':False}
    if kind == 'smoke':
        rows=read(out/'matrix.json')
        if fixed_rows(rows,SMOKE):
            result['complete']=all(r.get('executionStatus')=='completed' for r in rows)
            result['accepted']=all(r['ok'] for r in rows)
            result['qualified']=result['accepted'] and all(r.get('status')=='passed' and r.get('fidelity')=='qualified' for r in rows)
            result['failed']=result['complete'] and any(r.get('status')=='failed' and r.get('fidelity')=='qualified' for r in rows)
    elif kind in ('materials','events','d-regression'):
        names = MATERIALS if kind=='materials' else EVENTS if kind=='events' else TICKS
        data=read(out/('safe-summary.json' if kind=='d-regression' else 'summary.json'))
        rows=data.get('runs') if isinstance(data,dict) and kind=='d-regression' else data
        if fixed_rows(rows,names):
            key='D' if kind=='d-regression' else 'stage'
            expected=(['completed']*3+['failed']+['incomplete']*6 if kind=='d-regression' else
                      ['completed','failed','failed','incomplete'] if kind=='events' else
                      ['completed','failed']+['incomplete']*4)
            result['complete']=all(r.get('status')=='incomplete' and r.get(key) in ('completed','failed','incomplete') for r in rows)
            result['accepted']=result['complete'] and all(r['ok'] for r in rows) and [r[key] for r in rows]==expected
    elif kind=='d-compare':
        data=read(out/'safe-summary.json'); rows=data.get('runs') if isinstance(data,dict) else None
        result['complete']=(isinstance(rows,list) and len(rows)==3 and all(isinstance(r,dict) for r in rows)
                            and [r.get('count') for r in rows]==[60,600,600]
                            and all(type(r.get('count')) is int and type(r.get('equivalent')) is bool
                                    and type(r.get('sensitivity')) is bool and r.get('productD')=='completed' for r in rows))
        result['accepted']=result['complete'] and data.get('ok') is True and all(r['equivalent'] and r['sensitivity'] for r in rows)
    elif kind=='c-context':
        from tools.c_context_evidence import safe_cases
        data = read(out/'safe-summary.json')
        rows = safe_cases(data.get('cases')) if isinstance(data, dict) and type(data.get('schemaVersion')) is int and data['schemaVersion'] == 1 and data.get('c0Passed') is False else []
        result['contextCases'] = rows
        result['complete'] = len(rows) == 2 and all(r['executionStatus'] == 'completed' for r in rows)
        result['accepted'] = result['complete'] and all(r['gatePassed'] for r in rows)
    elif kind=='cow':
        data=read(out/'summary.json'); data=data if isinstance(data,dict) else {}
        rows=data.get('rows'); rows=rows if isinstance(rows,list) else []
        result['complete']=(len(rows)==10 and all(isinstance(r,dict) and type(r.get('repeat')) is int for r in rows)
                            and sorted((r.get('repeat'),r.get('mode','')) for r in rows)==[(n,m) for n in range(1,6) for m in ('copy','reflink')])
        result['accepted']=(result['complete'] and data.get('ok') is True and data.get('filesystem')=='dedicated-btrfs'
            and type(data.get('files')) is int and data['files']==516
            and type(data.get('sourceDataBytes')) is int and data['sourceDataBytes']>0
            and all(data.get(k) is True for k in ('crossDeviceFallback','staleHashesRejected','warmCache'))
            and data.get('metadataIncluded') is False
            and all(type(r.get('seconds')) in (int,float) and math.isfinite(r['seconds']) and r['seconds']>=0
                    and r.get('independent') is True and isinstance(r.get('modes'),dict)
                    and type(r['modes'].get(r['mode'])) is int and r['modes'][r['mode']]==1032
                    and type(r.get('additionalDataBytes')) is int
                    and (r['additionalDataBytes']==0 if r['mode']=='reflink' else r['additionalDataBytes']>=data['sourceDataBytes']*2)
                    for r in rows))
    return result
