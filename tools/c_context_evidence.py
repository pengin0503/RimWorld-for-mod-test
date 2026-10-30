"""Development C0 reachability checks. No product predicate or qualification."""
import hashlib
import json
import re

MARKER = '[RWMT-CONTEXT] '
LOG = re.compile(r'^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+\s+(ERROR|WARN|INFO)\s+\[([^\]]+)\] (.*)$')
STEAM_SHA256 = 'ee86ee64a1f2a1aad52ddca667ce8b7063ddaa952ce7a9c13ab5969a9d122eca'
STAGES = ('game', 'bill', 'binding', 'hooks', 'dialog', 'pane', 'complete')
EXCEPTIONS = ('none', 'missingApi', 'ambiguousApi', 'typeInitialization', 'nullReference', 'runtimeOther')
DIAGNOSTIC_TAGS = ('dependency', 'downloadUrl', 'description', 'packageId', 'supportedVersions',
                   'url', 'exception', 'graphics', 'GUI', 'window', 'patch', 'Harmony',
                   'Steam', 'NativeAllocationRuntime', 'Texture', 'camera', 'audio', 'frame', 'config')


def diagnostic_summary(evidence):
    errors = evidence.get('errors') if isinstance(evidence, dict) else None
    errors = errors if isinstance(errors, list) else ['invalid evidence']
    code = evidence.get('exitCode') if isinstance(evidence, dict) else None
    return {'exitCode': code if type(code) is int and -255 <= code <= 255 else None,
            'interrupted': not isinstance(evidence, dict) or evidence.get('interrupted') is not False,
            'errorCount': min(len(errors), 10000),
            'kinds': [[tag for tag in DIAGNOSTIC_TAGS if isinstance(error, str) and tag.lower() in error.lower()]
                      for error in errors[:16]]}


def parse_lines(lines, *, worker=False):
    from tools import validation_host as vh
    rows, errors = [], []
    observed = False
    for line in lines:
        text = line
        if worker:
            try:
                event = json.loads(line)
                if not isinstance(event, dict): raise ValueError()
            except (ValueError, TypeError):
                if not observed: errors.append('invalid worker record')
                continue
            text = event.get('message', '')
            if not isinstance(text, str):
                if not observed: errors.append('invalid worker message')
                continue
            if not observed and event.get('level') in ('error', 'warning') and not vh.known_noise(event):
                errors.append(text)
        else:
            match = LOG.match(line)
            if not observed and match and match[1] in ('ERROR', 'WARN'):
                level, category, message = match.groups()
                if not (level == 'ERROR' and category == 'Verse' and hashlib.sha256(message.encode()).hexdigest() == STEAM_SHA256):
                    errors.append(message)
            elif not observed and not match and re.search(r'\b(?:ERROR|WARN)\s+\[', line):
                errors.append(line)
        if MARKER not in text:
            continue
        try:
            row = json.loads(text.split(MARKER, 1)[1])
        except (ValueError, TypeError):
            errors.append('invalid context JSON')
            continue
        if len(rows) >= 16:
            errors.append('trace limit')
            break
        rows.append(row)
        if isinstance(row, dict) and row.get('phase') == 'marker':
            keys = {'phase', 'seq', 'sameGame', 'sameMap', 'finalizeCalls'}
            observed |= (set(row) == keys and type(row.get('seq')) is int and 1 <= row['seq'] <= 16
                         and type(row.get('finalizeCalls')) is int and 0 <= row['finalizeCalls'] <= 16
                         and all(type(row.get(k)) is bool for k in ('sameGame', 'sameMap')))
        elif isinstance(row, dict) and row.get('phase') == 'material':
            observed |= 'official.traceMalformed' not in material_gate(
                {'rows': [row], 'exitCode': 0, 'interrupted': False, 'errors': []})['stopReasons']
    return {'rows': rows, 'errors': errors}


def _execution(evidence):
    return (isinstance(evidence, dict) and type(evidence.get('exitCode')) is int
            and evidence['exitCode'] == 0 and evidence.get('interrupted') is False
            and evidence.get('errors') == [])


def event_gate(product, official):
    faults = set()
    phases = {}
    for label, evidence in (('product', product), ('official', official)):
        if not _execution(evidence):
            faults.add(label + '.diagnosticsOrExit')
        rows = evidence.get('rows') if isinstance(evidence, dict) else None
        valid = (isinstance(rows, list) and 2 <= len(rows) <= 16 and all(
            isinstance(r, dict) and set(r) == {'phase', 'seq', 'sameGame', 'sameMap', 'finalizeCalls'}
            and r.get('phase') in ('init', 'generated', 'finalize', 'marker')
            and type(r.get('seq')) is int and r['seq'] == i+1
            and type(r.get('sameGame')) is bool and type(r.get('sameMap')) is bool
            and type(r.get('finalizeCalls')) is int and 0 <= r['finalizeCalls'] <= 16
            for i, r in enumerate(rows)))
        phases[label] = [r['phase'] for r in rows] if valid else []
        if not valid:
            faults.add(label + '.traceMalformed')
            continue
        names = phases[label]
        if names.count('generated') != 1 or names.count('marker') != 1:
            faults.add(label + '.traceOrder')
            continue
        generated = names.index('generated'); marker = names.index('marker')
        if generated >= marker or names.count('init') > 1 or ('init' in names and names.index('init') >= generated):
            faults.add(label + '.traceOrder')
        if any(r['finalizeCalls'] != 0 for r in rows[:marker+1]) or 'finalize' in names[:marker]:
            faults.add(label + '.finalizedBeforeMarker')
        if not all(r['sameGame'] and r['sameMap'] for r in rows[generated:marker+1]):
            faults.add(label + '.contextChanged')
    return {'case': 'event', 'gatePassed': not faults, 'c0Passed': False,
            'stopReasons': sorted(faults), 'phases': phases}


def material_gate(evidence):
    faults = set()
    if not _execution(evidence):
        faults.add('official.diagnosticsOrExit')
    rows = evidence.get('rows') if isinstance(evidence, dict) else None
    valid = isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict)
    row = rows[0] if valid else {}
    keys = {'phase', 'freshGame', 'newBill', 'pane', 'ui', 'listing', 'row', 'returned', 'exception', 'allowed'}
    extra = {'setupStage', 'exceptionKind'} if 'setupStage' in row or 'exceptionKind' in row else set()
    valid = (valid and set(row) == keys | extra and row.get('phase') == 'material'
             and (not extra or row.get('setupStage') in STAGES and row.get('exceptionKind') in EXCEPTIONS)
             and all(type(row.get(k)) is bool for k in ('freshGame', 'newBill', 'returned', 'exception', 'allowed'))
             and all(type(row.get(k)) is int and 0 <= row[k] <= 20000 for k in ('pane', 'ui', 'listing', 'row')))
    if not valid:
        faults.add('official.traceMalformed')
    else:
        if not row['freshGame'] or not row['newBill']:
            faults.add('official.contextChanged')
        if row['exception'] or not row['returned']:
            faults.add('official.paneDidNotReturn')
        if not all(row[k] > 0 for k in ('pane', 'ui', 'listing', 'row')):
            faults.add('official.treeRowNotReached')
    result = {'case': 'material', 'gatePassed': not faults, 'c0Passed': False,
            'stopReasons': sorted(faults), 'reachability': {k: row[k] for k in ('pane', 'ui', 'listing', 'row')}
            if valid else {}}
    if valid and extra: result.update(setupStage=row['setupStage'], exceptionKind=row['exceptionKind'])
    return result


def safe_cases(rows):
    """Revalidate the fixed research result before public publication."""
    if not isinstance(rows, list) or len(rows) != 2:
        return []
    safe = []
    faults = {side + '.' + reason for side in ('product', 'official') for reason in
              ('diagnosticsOrExit', 'traceMalformed', 'traceOrder', 'finalizedBeforeMarker', 'contextChanged')}
    faults |= {'official.paneDidNotReturn', 'official.treeRowNotReached',
               'privatePreparationOrExecutionFailed', 'fixtureBuildFailed', 'product.observationIncomplete'}
    for expected, row in zip(('material', 'event'), rows):
        keys = {'case', 'gatePassed', 'c0Passed', 'stopReasons', 'executionStatus', 'phases', 'reachability', 'buildErrors', 'setupStage', 'exceptionKind', 'diagnostics'}
        if (not isinstance(row, dict) or not set(row) <= keys or row.get('case') != expected
                or row.get('c0Passed') is not False or type(row.get('gatePassed')) is not bool
                or row.get('executionStatus') not in ('completed', 'interrupted', 'notStarted')
                or not isinstance(row.get('stopReasons'), list) or len(row['stopReasons']) > 16
                or any(not isinstance(x, str) or x not in faults for x in row['stopReasons'])):
            return []
        result = {k: row[k] for k in ('case', 'gatePassed', 'c0Passed', 'stopReasons', 'executionStatus')}
        if 'setupStage' in row or 'exceptionKind' in row:
            if expected != 'material' or row.get('setupStage') not in STAGES or row.get('exceptionKind') not in EXCEPTIONS:
                return []
            result.update(setupStage=row['setupStage'], exceptionKind=row['exceptionKind'])
        if 'diagnostics' in row:
            diagnostics = row['diagnostics']
            if not isinstance(diagnostics, dict) or set(diagnostics) != {'product', 'official'}: return []
            for item in diagnostics.values():
                if (not isinstance(item, dict) or set(item) != {'exitCode', 'interrupted', 'errorCount', 'kinds'}
                        or item['exitCode'] is not None and (type(item['exitCode']) is not int or not -255 <= item['exitCode'] <= 255)
                        or type(item['interrupted']) is not bool or type(item['errorCount']) is not int
                        or not 0 <= item['errorCount'] <= 10000 or not isinstance(item['kinds'], list)
                        or len(item['kinds']) > 16 or any(not isinstance(k, list) or len(k) > len(DIAGNOSTIC_TAGS)
                            or any(tag not in DIAGNOSTIC_TAGS for tag in k) for k in item['kinds'])): return []
            result['diagnostics'] = diagnostics
        if 'buildErrors' in row:
            errors = row['buildErrors']
            if (not isinstance(errors, list) or len(errors) > 16 or any(not isinstance(e, dict)
                    or set(e) != {'source', 'line', 'code'} or e.get('source') not in ('CContext', 'MapProbe', 'EventChoice')
                    or type(e.get('line')) is not int or not 1 <= e['line'] <= 10000
                    or not isinstance(e.get('code'), str) or re.fullmatch('CS[0-9]{4}', e['code']) is None for e in errors)):
                return []
            result['buildErrors'] = errors
        proof = False
        if expected == 'event' and 'phases' in row:
            phases = row['phases']
            if (not isinstance(phases, dict) or set(phases) != {'product', 'official'}
                    or any(not isinstance(p, list) or len(p) > 16 or any(x not in ('init', 'generated', 'finalize', 'marker') for x in p) for p in phases.values())):
                return []
            result['phases'] = phases
            proof = all(p.count('generated') == p.count('marker') == 1
                        and p.index('generated') < p.index('marker')
                        and 'finalize' not in p[:p.index('marker')] for p in phases.values())
        if expected == 'material' and 'reachability' in row:
            counts = row['reachability']
            if (not isinstance(counts, dict) or (counts and set(counts) != {'pane', 'ui', 'listing', 'row'})
                    or any(type(x) is not int or not 0 <= x <= 20000 for x in counts.values())):
                return []
            result['reachability'] = counts
            proof = bool(counts) and all(x > 0 for x in counts.values())
        if row['gatePassed'] and (row['stopReasons'] or row['executionStatus'] != 'completed' or not proof):
            return []
        safe.append(result)
    return safe
