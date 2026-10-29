"""Fixed D request and independently checked real-game tick evidence."""
import re

CASE = 'bounded-tick.v1'
OBSERVER_VERSION = 1
INITIALIZATION = 'gameFinalizeInitAndStartedNewGame'
OBSERVERS = {'fixture.counter'}
ID = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,127}')


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def validate_tick(value, levels, tests, map_request, rows):
    if 'D' not in levels:
        if value is not None or rows:
            raise ValueError('tick and tickObservations need level D')
        return None
    if set(levels) != {'A', 'D'} or tests != [CASE] or map_request is None:
        raise ValueError('D v1 requires only A/D, bounded-tick.v1 and a generated map')
    if not isinstance(value, dict) or set(value) != {'count', 'observeAt'}:
        raise ValueError('tick needs exactly count and observeAt')
    count, points = value['count'], value['observeAt']
    if not integer(count) or not 1 <= count <= 60000:
        raise ValueError('tick.count must be an integer 1..60000')
    if (not isinstance(points, list) or not 1 <= len(points) <= 64
            or not all(integer(n) and 0 <= n <= count for n in points)
            or points != sorted(set(points)) or points[-1] != count):
        raise ValueError('observeAt needs 1..64 sorted distinct ticks 0..count including count')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 64:
        raise ValueError('D needs 1..64 tickObservations')
    seen = set()
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'tick', 'id', 'equals'}
                or not integer(row['tick']) or row['tick'] not in points
                or not isinstance(row['id'], str) or not ID.fullmatch(row['id'])
                or not integer(row['equals']) or not -(2**63) <= row['equals'] < 2**63):
            raise ValueError('tickObservations need an observed tick, safe ID and Int64 equals')
        pair = (row['tick'], row['id'])
        if pair in seen:
            raise ValueError('tick/id observations must be distinct')
        seen.add(pair)
    return {'count': count, 'observeAt': list(points)}


def evidence_complete(config, evidence):
    """Do not trust a Worker completion flag or host-side loop count."""
    if not isinstance(evidence, dict):
        return False
    if (evidence.get('caseId') != CASE or evidence.get('observerVersion') != OBSERVER_VERSION
            or isinstance(evidence.get('observerVersion'), bool)
            or evidence.get('initialization') != INITIALIZATION or evidence.get('status') != 'completed'):
        return False
    start, end, advanced = (evidence.get(k) for k in ('startTick', 'endTick', 'advanced'))
    if (not all(integer(n) and 0 <= n <= 2**31-1 for n in (start, end, advanced))
            or end - start != config['count'] or advanced != config['count']):
        return False
    observations = evidence.get('observations')
    if not isinstance(observations, list) or len(observations) != len(config['observeAt']):
        return False
    for point, row in zip(config['observeAt'], observations):
        if (not isinstance(row, dict) or not integer(row.get('tick')) or row['tick'] != point
                or not integer(row.get('gameTick')) or row['gameTick'] != start + point):
            return False
        values = row.get('values')
        if (not isinstance(values, dict) or set(values) != OBSERVERS
                or not all(integer(n) and -(2**63) <= n < 2**63 for n in values.values())):
            return False
    return True


def evaluate_tick(request, evidence):
    stage = {'status': 'incomplete', 'fidelity': 'experimental', 'checks': [], 'evidence': evidence}
    incomplete = [{'code': 'dNotQualified', 'detail': 'bounded-tick.v1 has no independent qualification'}]
    failed = []
    expected = request['expectations']['tickObservations']
    if (not evidence_complete(request['tick'], evidence)
            or any(row['id'] not in OBSERVERS for row in expected)):
        incomplete.append({'code': 'tickObservationIncomplete',
                           'detail': 'missing, interrupted, unknown or inconsistent real-game tick observations'})
        return stage, incomplete, failed
    actual = {row['tick']: row['values'] for row in evidence['observations']}
    for row in expected:
        value = actual[row['tick']][row['id']]
        stage['checks'].append({'tick': row['tick'], 'id': row['id'], 'expected': row['equals'],
                                'actual': value, 'outcome': 'match' if value == row['equals'] else 'mismatch'})
    stage['status'] = 'completed'
    if any(row['outcome'] == 'mismatch' for row in stage['checks']):
        stage['status'] = 'failed'
        failed.append({'code': 'tickObservationMismatch', 'detail': 'observed fixture state differs from expectation'})
    return stage, incomplete, failed


def load_checkpoint(run_dir, run_id, nonce):
    """Recover bounded partial evidence after a kill, never a successful result."""
    import json
    try:
        path = run_dir / 'tick-evidence.json'
        if path.stat().st_size > 1024 * 1024:
            return None
        row = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(row, dict) or row.get('recordType') != 'rwmtTickCheckpoint'
                or type(row.get('schemaVersion')) is not int or row['schemaVersion'] != 1
                or row.get('runId') != run_id or row.get('nonce') != nonce or not isinstance(row.get('tick'), dict)):
            return None
        return {**row['tick'], 'status': 'incomplete'}
    except (OSError, ValueError, UnicodeError):
        return None
