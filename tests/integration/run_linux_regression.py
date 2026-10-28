"""Private R2 regression and timings. Only a whitelisted summary is public."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from tools import codex_workflow as cw, validation_host as vh


def loader_order_matches(observed, wanted):
    if not isinstance(observed, dict) or observed.get('matches') is not True:
        return False
    actual = [s.casefold() for s in observed.get('actual', []) if not s.casefold().startswith('ludeon.')]
    return actual == wanted


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase', choices=('prepare', 'run'))
    p.add_argument('--root', required=True)
    p.add_argument('--worker', default='worker/bin')
    a = p.parse_args()
    root = cw._safe_private(Path(a.root))
    if a.phase == 'prepare':
        stage = 'modMetadataAndPayload'
        try:
            # Fail on unavailable/ambiguous MOD inputs before expensive runtime acquisition.
            selected = cw.fetch_mods(SimpleNamespace(private_root=root, refresh=False, aws='aws',
                index_zip=None, target='Vanilla Psycasts Expanded', local_target=None,
                dependency=[], official=['Core', 'Royalty'], language='English', scope='validation'))
            stage = 'gameRuntimeAndSnapshot'
            prepared = cw.prepare(SimpleNamespace(private_root=root, refresh=False, aws='aws'))
        except Exception as error:
            code = getattr(error, 'code', 'preparationError')
            # Codes are selected by our tools, never copy exception messages or paths.
            (root / 'safe-summary.json').write_text(json.dumps({
                'ok': False, 'stage': stage, 'errorType': type(error).__name__, 'code': code}))
            raise
        (root / 'preparation-summary.json').write_text(json.dumps({
            'gameFiles': prepared.get('files'), 'gameR2': prepared.get('r2'),
            'modCount': len(selected['fetched']),
            'modSelectedBytes': sum(x['r2']['listedBytes'] for x in selected['fetched']),
            'modSelectedFiles': sum(x['r2']['selected'] for x in selected['fetched'])}))
        return 0
    # Separate process from preparation: no R2 credentials in this phase.
    snapshot = root / 'game-snapshot'
    request = root / 'request.json'
    results = []
    for name, cache in [('uncached-1', False), ('uncached-2', False), ('cache-fill', True),
                        ('cached-1', True), ('cached-2', True)]:
        r = vh.run_validation(snapshot, request, root / name, a.worker,
            baseline_cache=root / 'baseline-cache' if cache else None,
            hash_cache=root / 'hash-cache.json' if cache else None)
        wanted = [m['packageId'].casefold() for m in json.loads(request.read_text())['mods']]
        ok = r['status'] == 'passed' and loader_order_matches(r.get('modOrder'), wanted)
        results.append({'case': name, 'ok': ok, 'status': r['status'],
            'reasons': [x['code'] for x in r.get('reasons', [])],
            'baselineCached': r.get('diagnostics', {}).get('baselineCached'),
            'timings': r.get('timings'),
            'copyModes': r.get('process', {}).get('target', {}).get('modCopyModes')})
    summary = {'preparation': json.loads((root / 'preparation-summary.json').read_text()), 'runs': results}
    for label, script in [('event', 'run_event_choice.py'), ('materials', 'run_bill_ingredients.py')]:
        cmd = [sys.executable, str(REPO / 'tests/integration' / script), '--snapshot', str(snapshot),
               '--worker', str(Path(a.worker).resolve()), '--out', str(root / label)]
        with (root / (label + '.log')).open('w') as log:
            completed = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
        summary[label + 'Regression'] = completed.returncode == 0
    ok = (all(x['ok'] for x in results) and all(x['baselineCached'] for x in results[-2:])
          and summary['eventRegression'] and summary['materialsRegression'])
    summary['ok'] = ok
    (root / 'safe-summary.json').write_text(json.dumps(summary, indent=2))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
