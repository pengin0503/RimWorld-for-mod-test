"""Measure one private initial preparation, reuse it, and validate A only."""
import argparse
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from tools import codex_workflow as cw, validation_host as vh

PREPARATION_TIMES = ('fetchSeconds', 'snapshotCopySeconds', 'snapshotHashSeconds',
                     'snapshotTotalSeconds', 'totalSeconds')
R2_COUNTS = ('selected', 'skipped', 'listedBytes', 'downloaded', 'cached')


def mapping(value):
    return value if isinstance(value, dict) else {}


def numbers(value, keys, *, integer=False):
    data = mapping(value)
    types = (int,) if integer else (int, float)
    return {key: data[key] for key in keys if type(data.get(key)) in types
            and 0 <= data[key] <= 10**15}


def enum(value, allowed):
    return value if isinstance(value, str) and value in allowed else 'unknown'


def public_summary(data):
    """Rebuild output: never forward paths, diagnostics, arbitrary strings or NaN."""
    data = mapping(data)
    prepared, validation = mapping(data.get('preparation')), mapping(data.get('validation'))
    version = prepared.get('version')
    if not isinstance(version, str) or not re.fullmatch(r'\d{1,3}\.\d{1,3}\.\d{1,6} rev\d{1,6}', version):
        version = 'unknown'
    result = {
        'preparation': {
            'status': enum(prepared.get('status'), ('prepared', 'snapshotReused')),
            'version': version,
            **numbers(prepared, ('files',), integer=True),
            'r2': numbers(prepared.get('r2'), R2_COUNTS, integer=True),
            'timings': numbers(prepared.get('timings'), PREPARATION_TIMES)},
        'mods': numbers(data.get('mods'), ('count', 'files', 'bytes'), integer=True),
        'snapshotReused': data.get('snapshotReused') is True,
        'validation': {
            'status': enum(validation.get('status'), ('passed', 'failed', 'blocked', 'incomplete')),
            'executionStatus': enum(validation.get('executionStatus'), ('completed', 'notStarted', 'interrupted')),
            'fidelity': enum(validation.get('fidelity'), ('qualified', 'experimental')),
            'modOrderMatches': (validation.get('modOrderMatches') is True
                                or mapping(validation.get('modOrder')).get('matches') is True),
            'timings': numbers(validation.get('timings'), ('totalSeconds',))}}
    check = result['validation']
    result['ok'] = (result['preparation']['status'] == 'prepared' and result['snapshotReused']
                    and check['status'] == 'passed' and check['executionStatus'] == 'completed'
                    and check['fidelity'] == 'qualified' and check['modOrderMatches'])
    return result


def read_summary(root):
    path = root / 'safe-summary.json'
    try:
        if path.stat().st_size > 64 * 1024:
            return {}
        return mapping(json.loads(path.read_text(encoding='utf-8')))
    except (OSError, ValueError):
        return {}


def write_summary(root, data):
    (root / 'safe-summary.json').write_text(
        json.dumps(public_summary(data), allow_nan=False, indent=2), encoding='utf-8')


def validate_a(root, worker):
    request = root / 'request.json'
    body = json.loads(request.read_text(encoding='utf-8'))
    if (body.get('levels') != ['A'] or body.get('official') != ['Core']
            or body.get('language') != 'English' or 'map' in body or 'tests' in body
            or body.get('expectations', {}) != {}):
        raise cw.WorkflowError('measurement is restricted to A / Core / English')
    with cw._no_cloud_credentials():
        return vh.run_validation(root / 'game-snapshot', request, root / 'a-result', worker)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'run', 'publish'))
    parser.add_argument('--root', required=True)
    parser.add_argument('--worker', default='worker/bin')
    args = parser.parse_args(argv)
    root = cw._safe_private(Path(args.root))
    data = read_summary(root)
    if args.phase == 'publish':
        print(json.dumps(public_summary(data), allow_nan=False, indent=2))
        return 0
    if args.phase == 'prepare':
        data = {}
        write_summary(root, data)
        if (root / 'game-snapshot').exists():
            raise cw.WorkflowError('initial measurement requires a fresh private root')
        selected = cw.fetch_mods(SimpleNamespace(private_root=root, refresh=False, aws='aws',
            index_zip=None, target='Harmony', local_target=None, dependency=[],
            official=['Core'], language='English', scope='validation'))
        data['mods'] = {'count': len(selected['fetched']),
            'files': sum(x['r2']['selected'] for x in selected['fetched']),
            'bytes': sum(x['r2']['listedBytes'] for x in selected['fetched'])}
        data['preparation'] = cw.prepare(SimpleNamespace(private_root=root, refresh=False, aws='aws'))
        write_summary(root, data)
        reused = cw.prepare(SimpleNamespace(private_root=root, refresh=False, aws='aws'))
        data['snapshotReused'] = reused['status'] == 'snapshotReused'
    else:
        data['validation'] = {}
        write_summary(root, data)
        data['validation'] = validate_a(root, Path(args.worker).resolve())
    write_summary(root, data)
    return 0 if args.phase == 'prepare' or public_summary(data)['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
