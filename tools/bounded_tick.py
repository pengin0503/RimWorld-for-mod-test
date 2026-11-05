"""Fixed D request and independently checked real-game tick evidence."""
import re

CASE = 'bounded-tick.v1'
CASE_V2 = 'bounded-tick.v2'
OBSERVER_VERSION = 1
INITIALIZATION = 'gameFinalizeInitAndStartedNewGame'
OBSERVERS = {'fixture.counter'}
OBSERVERS_V2 = {'fixture.counter', 'game.tick'}


def case_id(config):
    return CASE_V2 if isinstance(config, dict) and 'observers' in config else CASE


def observer_version(config):
    return 2 if case_id(config) == CASE_V2 else OBSERVER_VERSION


def cache_identity(config):
    return {'caseId': case_id(config), 'observerVersion': observer_version(config)}

ID = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,127}')


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def validate_tick(value, levels, tests, map_request, rows):
    if 'D' not in levels:
        if value is not None or rows:
            raise ValueError('tick and tickObservations need level D')
        return None
    if set(levels) != {'A', 'D'} or tests not in ([CASE], [CASE_V2]) or map_request is None:
        raise ValueError('D requires only A/D, a supported bounded-tick case and a generated map')
    v2 = tests == [CASE_V2]
    expected = {'count', 'observeAt', 'observers'} if v2 else {'count', 'observeAt'}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError('tick fields do not match the selected D case')
    observers = None
    if v2:
        observers = value['observers']
        if (not isinstance(observers, list) or not 1 <= len(observers) <= 2
                or any(not isinstance(name, str) or name not in OBSERVERS_V2 for name in observers)
                or observers != sorted(set(observers))):
            raise ValueError('v2 observer registry must be sorted, unique, and allowlisted')
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
        if v2 and row['id'] not in observers:
            raise ValueError('v2 requires explicitly registered observer IDs')
        seen.add(pair)
    if v2 and not set(observers) <= {row['id'] for row in rows}:
        raise ValueError('every v2 observer must have an expectation')
    result = {'count': count, 'observeAt': list(points)}
    if v2:
        result['observers'] = list(observers)
    return result


def validated_prefix(config, evidence):
    """Return only a structurally consistent prefix, including interrupted evidence."""
    if not isinstance(evidence, dict):
        return None
    if (evidence.get('caseId') != case_id(config) or type(evidence.get('observerVersion')) is not int
            or evidence['observerVersion'] != observer_version(config)
            or evidence.get('initialization') != INITIALIZATION):
        return None
    start, end, advanced = (evidence.get(k) for k in ('startTick', 'endTick', 'advanced'))
    if (not all(integer(n) and 0 <= n <= 2**31-1 for n in (start, end, advanced))
            or end - start != advanced or not 0 <= advanced <= config['count']):
        return None
    observations = evidence.get('observations')
    if not isinstance(observations, list) or len(observations) > len(config['observeAt']):
        return None
    actual = {}
    for point, row in zip(config['observeAt'], observations):
        if (not isinstance(row, dict) or not integer(row.get('tick')) or row['tick'] != point
                or point > advanced or not integer(row.get('gameTick')) or row['gameTick'] != start + point):
            return None
        values = row.get('values')
        expected_ids = set(config['observers']) if 'observers' in config else OBSERVERS
        if (not isinstance(values, dict) or set(values) != expected_ids
                or not all(integer(n) and -(2**63) <= n < 2**63 for n in values.values())):
            return None
        if 'game.tick' in values and values['game.tick'] != row['gameTick']:
            # The Worker claims this is the real TickManager value: a
            # disagreement with its own raw gameTick means corrupt evidence.
            return None
        actual[point] = values
    return actual


def evidence_complete(config, evidence):
    actual = validated_prefix(config, evidence)
    return (actual is not None and evidence.get('status') == 'completed' and not evidence.get('error')
            and evidence['advanced'] == config['count'] and len(actual) == len(config['observeAt']))


def evaluate_tick(request, evidence, *, interrupted=False):
    stage = {'status': 'incomplete', 'fidelity': 'experimental', 'checks': [], 'evidence': evidence}
    incomplete = [{'code': 'dNotQualified', 'detail': 'bounded-tick.v1 has no independent qualification'}]
    failed = []
    actual = validated_prefix(request['tick'], evidence)
    unavailable = interrupted or not evidence_complete(request['tick'], evidence)
    for row in request['expectations']['tickObservations']:
        check = {'tick': row['tick'], 'id': row['id'], 'expected': row['equals']}
        permitted = set(request['tick']['observers']) if 'observers' in request['tick'] else OBSERVERS
        if actual is None or row['tick'] not in actual or row['id'] not in permitted:
            check.update(actual=None, outcome='error')
            unavailable = True
        else:
            value = actual[row['tick']][row['id']]
            check.update(actual=value, outcome='match' if value == row['equals'] else 'mismatch')
        stage['checks'].append(check)
    if unavailable:
        incomplete.append({'code': 'tickObservationIncomplete',
                           'detail': 'missing, interrupted, unknown or inconsistent real-game tick observations'})
    else:
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
