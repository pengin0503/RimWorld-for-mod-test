"""Private, main-bound acquisition for the C reference metadata audit."""
import hashlib
import json
import math
import os
import shutil
import time
from pathlib import Path
from tools import codex_workflow as cw, private_validation as pv, validation_host as vh

ADAPTER = vh.ADAPTERS['rimworld-1.7.4985-rev1269']
EXPECTED = {**ADAPTER['sha256'], **ADAPTER['qualified'][('linux-x64', 'waylith')]['runtimeSha256']}
VERSION = '1.7.4985 rev1269'
MANAGED_NAMES = frozenset(('Assembly-CSharp.dll', 'RimWorld.dll', 'Waylith.dll', 'UnityStubs.dll', 'Waylith.UnityCompat.dll'))
RUNTIME_NAMES = frozenset(('libcoreclr.so', 'System.Private.CoreLib.dll'))


def verify_directory(directory):
    directory = Path(directory)
    try:
        if directory.is_symlink() or (directory/'Version.txt').is_symlink(): return False
        version = directory/'Version.txt'
        if version.stat().st_size > 128: return False
        with version.open('rb') as stream: version_bytes = stream.read(129)
        if version_bytes not in (VERSION.encode(), (VERSION+'\n').encode(), (VERSION+'\r\n').encode()): return False
        total = version.stat().st_size
        for name, digest in EXPECTED.items():
            path = directory/name
            if path.is_symlink() or not path.is_file(): return False
            size = path.stat().st_size
            if not 0 < size <= 64 * 1024 * 1024: return False
            total += size
            if total > 128 * 1024 * 1024: return False
            sha = hashlib.sha256()
            with path.open('rb') as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b''): sha.update(chunk)
            if sha.hexdigest() != digest: return False
        return True
    except (OSError, UnicodeError): return False


def session_path(root):
    return Path(root) / 'static-audit' / pv.current_identity()['runId']


def verify(root):
    return verify_directory(session_path(root) / 'input')


def valid_snapshot_file(path, name):
    try:
        if path.is_symlink() or not path.is_file(): return False
        size = path.stat().st_size
        if not 0 < size <= 64 * 1024 * 1024: return False
        if name == 'Version.txt':
            return size <= 128 and path.read_bytes() in (VERSION.encode(), (VERSION+'\n').encode(), (VERSION+'\r\n').encode())
        sha = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''): sha.update(chunk)
        return sha.hexdigest() == EXPECTED[name]
    except (OSError, KeyError): return False


def prepare(root):
    identity = pv.current_identity()
    started = time.monotonic()
    runtime_hashes = ADAPTER.get('qualified', {}).get(('linux-x64', 'waylith'), {}).get('runtimeSha256', {})
    if set(ADAPTER.get('sha256', {})) != MANAGED_NAMES or set(runtime_hashes) != RUNTIME_NAMES:
        raise ValueError('adapter input set changed')
    if any(not isinstance(v, str) or len(v) != 64 or any(c not in '0123456789abcdef' for c in v) for v in (*ADAPTER['sha256'].values(), *runtime_hashes.values())):
        raise ValueError('invalid adapter digest')
    root = cw._safe_private(Path(root))
    parent = root / 'static-audit'
    if parent.is_symlink(): raise ValueError('invalid audit directory')
    parent.mkdir(mode=0o700, exist_ok=True)
    session = session_path(root)
    try:
        session.mkdir(mode=0o700, exist_ok=False)
    except FileExistsError:
        if session.is_dir() and not session.is_symlink():
            pv.write_json(session/'manifest.json', {**identity, 'verified': False, 'invalidated': True})
        raise ValueError('audit session already exists') from None
    directory = session/'input'; directory.mkdir(mode=0o700)
    manifest = {**identity, 'repository': os.environ['GITHUB_REPOSITORY'], 'ref': os.environ['GITHUB_REF'], 'verified': False}
    pv.write_json(session/'manifest.json', manifest)
    names = ['Version.txt', *EXPECTED]
    snapshot = root / 'game-snapshot' / 'game'
    reusable = set()
    if not any(p.is_symlink() for p in (snapshot, snapshot.parent)):
        reusable = {name for name in names if valid_snapshot_file(snapshot/name, name)}
    if len(reusable) < len(names):
        with cw.r2_session('aws') as client:
            items = []
            for name in names:
                key = 'Game-Linux/'+name
                matches = [x for x in client.list_static_audit_key(key) if x.get('key') == key]
                if len(matches) != 1 or type(matches[0].get('size')) is not int or not 0 < matches[0]['size'] <= 64*1024*1024:
                    raise ValueError('invalid fixed input metadata')
                items.extend(matches)
            if sum(x['size'] for x in items) > 128*1024*1024: raise ValueError('input budget exceeded')
            for item in items:
                name = item['key'].removeprefix('Game-Linux/')
                if name in reusable:
                    shutil.copyfile(snapshot/name, directory/name)
                else:
                    client.get(item['key'], directory/name, item['size'], refresh=False)
                    if (directory/name).is_symlink() or (directory/name).stat().st_size != item['size']:
                        raise ValueError('downloaded input size mismatch')
    else:
        for name in names: shutil.copyfile(snapshot/name, directory/name)
    if not verify(root): raise ValueError('input identity mismatch')
    inputs = {}
    for name in names:
        path = directory/name
        inputs[name] = {'size': path.stat().st_size, 'sha256': vh.sha256_file(path),
                        'source': 'snapshot' if name in reusable else 'r2'}
    manifest.update(verified=True, files=len(names), bytes=sum(x['size'] for x in inputs.values()),
                    inputs=inputs, seconds=round(time.monotonic() - started, 3))
    pv.write_json(session/'manifest.json', manifest)
    return manifest


def load_session(root):
    identity = pv.current_identity()
    root = cw._safe_private(Path(root))
    session = session_path(root)
    manifest_file = session / 'manifest.json'
    if session.parent.is_symlink() or session.is_symlink() or manifest_file.is_symlink() or not manifest_file.is_file() or manifest_file.stat().st_size > 65536:
        raise ValueError('invalid audit manifest')
    manifest = pv.read_json(manifest_file)
    if not isinstance(manifest, dict) or any(manifest.get(k) != v for k, v in identity.items()) or manifest.get('repository') != os.environ['GITHUB_REPOSITORY'] or manifest.get('ref') != os.environ['GITHUB_REF'] or manifest.get('verified') is not True or manifest.get('invalidated') is True or not verify(root):
        raise ValueError('unverified audit session')
    inputs = manifest.get('inputs')
    names = ['Version.txt', *EXPECTED]
    if not isinstance(inputs, dict) or set(inputs) != set(names): raise ValueError('invalid audit inputs')
    for name in names:
        entry = inputs[name]
        path = session / 'input' / name
        if not isinstance(entry, dict) or type(entry.get('size')) is not int or entry['size'] != path.stat().st_size or entry.get('sha256') != vh.sha256_file(path) or entry.get('source') not in ('r2', 'snapshot'):
            raise ValueError('changed audit input')
    return manifest


def scan(root, scanner):
    identity = pv.current_identity()
    manifest = load_session(root)
    session = session_path(root)
    result_path = session / 'scan.json'
    if result_path.exists() or result_path.is_symlink():
        if not result_path.is_symlink():
            pv.write_json(result_path, {**identity, 'verified': False, 'invalidated': True})
        raise ValueError('scanner already attempted')
    pv.write_json(result_path, {**identity, 'verified': False})
    start = time.monotonic()
    results = []
    total_output = 0
    total_logs = 0
    limits = {'methods': 128, 'ilBytes': 1024*1024, 'instructions': 100000, 'calls': 4096}
    totals = {name: 0 for name in limits}
    for index, name in enumerate(ADAPTER['sha256']):
        remaining = 120 - (time.monotonic() - start)
        if remaining <= 0: raise ValueError('scanner timeout')
        output = session / ('scan-' + str(index) + '.json')
        command = ['dotnet', str(scanner), str(session/'input'/name), EXPECTED[name], str(output)]
        log = session/('scan-' + str(index) + '.log')
        process = pv.run_command(command, log, timeout=remaining, memory_limit=2*1024**3)
        if log.exists(): total_logs += log.stat().st_size
        if total_logs > 8*1024*1024: raise ValueError('scanner log budget exceeded')
        if process.get('exitCode') != 0 or process.get('interrupted') is not False:
            raise ValueError('scanner did not finish')
        if output.is_symlink() or not output.is_file() or output.stat().st_size > 4*1024*1024:
            raise ValueError('invalid scanner output')
        total_output += output.stat().st_size
        if total_output > 4*1024*1024: raise ValueError('scanner output budget exceeded')
        result = pv.read_json(output)
        if not isinstance(result, dict) or result.get('sha256') != EXPECTED[name] or not isinstance(result.get('types'), list):
            raise ValueError('scanner identity mismatch')
        metrics = result.get('metrics')
        if not isinstance(metrics, dict) or set(metrics) != set(limits): raise ValueError('invalid scanner metrics')
        for metric, limit in limits.items():
            value = metrics[metric]
            if type(value) is not int or value < 0: raise ValueError('invalid scanner metric')
            totals[metric] += value
            if totals[metric] > limit: raise ValueError('scanner budget exceeded')
        results.append(result)
    load_session(root)
    types = []
    for target in TARGETS:
        rows = [row for result in results for row in result['types'] if isinstance(row, dict) and row.get('id') == target]
        found = [row for row in rows if row.get('found') is True]
        if len(rows) != len(results) or len(found) > 1: raise ValueError('ambiguous scanner output')
        if found: types.append(found[0])
        elif rows: types.append(rows[0])
    combined = {**identity, 'verified': True, 'types': types}
    pv.write_json(result_path, combined)
    return combined


PRIMITIVES = frozenset(('Void', 'Boolean', 'Char', 'SByte', 'Byte', 'Int16', 'UInt16', 'Int32', 'UInt32', 'Int64', 'UInt64', 'Single', 'Double', 'String', 'Object', 'IntPtr', 'UIntPtr'))
TYPE_ATOMS = frozenset(('System.Action', 'System.Collections.Generic.List`1', 'System.Collections.Generic.IEnumerable`1',
    'Verse.Game', 'Verse.MapGenerator', 'Verse.LongEventHandler', 'RimWorld.Dialog_BillConfig', 'Verse.ThingFilterUI',
    'Verse.Listing_TreeThingFilter', 'RimWorld.BillUtility', 'RimWorld.IncidentWorker', 'Verse.DiaOption',
    'Verse.ThingFilter', 'Verse.ThingDef', 'Verse.SpecialThingFilterDef', 'Verse.TreeNode_ThingCategory',
    'Verse.RecipeDef', 'Verse.IntVec3', 'Verse.Map', 'Verse.MapGeneratorDef', 'Verse.GenStepWithParams',
    'RimWorld.QuickSearchFilter', 'RimWorld.Precept_ThingStyle', 'RimWorld.Planet.MapParent', 'UnityEngine.Rect', 'UnityEngine.Vector2'))


def normalized_type(node, depth=0):
    if depth >= 8 or not isinstance(node, dict): raise ValueError('unsupported type')
    kind = node.get('kind')
    allowed = {'primitive': {'kind', 'name'}, 'named': {'kind', 'name'}, 'methodParameter': {'kind', 'index'}, 'typeParameter': {'kind', 'index'}, 'byref': {'kind', 'element'}, 'pointer': {'kind', 'element'}, 'array': {'kind', 'element', 'rank'}, 'generic': {'kind', 'element', 'arguments'}}
    if kind not in allowed or set(node) != allowed[kind]: raise ValueError('invalid type schema')
    if kind == 'primitive' and node.get('name') in PRIMITIVES: return 'System.' + node['name']
    if kind == 'named' and node.get('name') in TYPE_ATOMS: return node['name']
    if kind in ('methodParameter', 'typeParameter') and type(node.get('index')) is int and 0 <= node['index'] < 32:
        return ('!!' if kind == 'methodParameter' else '!') + str(node['index'])
    if kind in ('byref', 'pointer'):
        return normalized_type(node.get('element'), depth+1) + ('&' if kind == 'byref' else '*')
    if kind == 'array' and type(node.get('rank')) is int and 1 <= node['rank'] <= 32:
        return normalized_type(node.get('element'), depth+1) + '[' + ',' * (node['rank']-1) + ']'
    if kind == 'generic' and isinstance(node.get('arguments'), list) and 1 <= len(node['arguments']) <= 32:
        return normalized_type(node.get('element'), depth+1) + '<' + ','.join(normalized_type(x, depth+1) for x in node['arguments']) + '>'
    raise ValueError('unsupported type')


TARGETS = {'game': ('InitNewGame', 'FinalizeInit'), 'map-generator': ('GenerateMap',),
           'long-events': ('ExecuteWhenFinished', 'QueueLongEvent'),
           'bill-dialog': ('DoIngredientConfigPane', 'get_HiddenSpecialThingFilters'),
           'filter-ui': ('DoThingFilterConfigWindow',), 'filter-listing': ('.ctor', 'Visible'),
           'bill-factory': ('MakeNewBill',), 'incident': ('TryExecute',), 'dialog-choice': ('Activate',)}
TARGET_NAMES = {'game': 'Verse.Game', 'map-generator': 'Verse.MapGenerator', 'long-events': 'Verse.LongEventHandler',
                'bill-dialog': 'RimWorld.Dialog_BillConfig', 'filter-ui': 'Verse.ThingFilterUI',
                'filter-listing': 'Verse.Listing_TreeThingFilter', 'bill-factory': 'RimWorld.BillUtility',
                'incident': 'RimWorld.IncidentWorker', 'dialog-choice': 'Verse.DiaOption'}
VISIBILITY = {'Public': 'public', 'Private': 'private', 'Family': 'family', 'Assembly': 'assembly',
              'FamANDAssem': 'family-and-assembly', 'FamORAssem': 'family-or-assembly', 'PrivateScope': 'private-scope'}


def public_summary(raw, identity):
    raw = raw if isinstance(raw, dict) else {}
    bound = all(raw.get(k) == v for k, v in identity.items())
    binary = bound and raw.get('verified') is True
    source = raw.get('types') if binary and isinstance(raw.get('types'), list) else []
    rows = []
    try:
        encoded = json.dumps(raw, allow_nan=False)
        finite = len(encoded.encode('utf-8')) <= 4*1024*1024
    except (ValueError, TypeError, RecursionError): finite = False
    complete = binary and finite and set(raw) == {'runId', 'commit', 'verified', 'types'} and len(source) == len(TARGETS)
    allowed_edges = {TARGET_NAMES[k] + '.' + n: (k, n) for k, values in TARGETS.items() for n in values}
    for target_id, names in TARGETS.items():
        matches = [x for x in source if isinstance(x, dict) and x.get('id') == target_id]
        if len(matches) != 1: complete = False; continue
        target = matches[0]
        if set(target) != {'id', 'found', 'methods'}: complete = False
        if type(target.get('found')) is not bool or not isinstance(target.get('methods'), list):
            complete = False; continue
        methods = []
        for name in names:
            entries = [x for x in target['methods'] if isinstance(x, dict) and x.get('name') == name]
            if len(entries) != 1 or not isinstance(entries[0].get('overloads'), list) or len(entries[0]['overloads']) > 16:
                complete = False; methods.append({'name': name, 'status': 'unreadable', 'signatures': []}); continue
            if set(entries[0]) != {'name', 'overloads'}: complete = False
            signatures = []; edges = []; overloads = []; unreadable = False; unreadable_tokens = []
            if not target['found'] and entries[0]['overloads']:
                complete = False; methods.append({'name': name, 'status': 'unreadable', 'signatures': []}); continue
            for item in entries[0]['overloads']:
                try:
                    if isinstance(item, dict) and not set(item).issubset({'token', 'return', 'parameters', 'genericCount', 'static', 'visibility', 'calls', 'branches', 'exceptions'}): complete = False
                    if not isinstance(item, dict) or type(item.get('static')) is not bool or item.get('visibility') not in VISIBILITY:
                        raise ValueError('invalid method')
                    params = item.get('parameters'); generics = item.get('genericCount')
                    if not isinstance(params, list) or len(params) > 64 or type(generics) is not int or not 0 <= generics <= 32:
                        raise ValueError('invalid signature')
                    result = normalized_type(item.get('return'))
                    signature = ('static' if item['static'] else 'instance') + ' ' + VISIBILITY[item['visibility']] + ' ' + result
                    if generics: signature += '<' + str(generics) + '>'
                    signature += ' (' + ', '.join(normalized_type(x) for x in params) + ')'
                    if len(signature) > 2048: raise ValueError('signature too long')
                    branches = item.get('branches', [])
                    regions = item.get('exceptions', [])
                    if not isinstance(branches, list) or len(branches) > 100000 or not isinstance(regions, list) or len(regions) > 65536:
                        raise ValueError('invalid control flow')
                    for branch in branches:
                        if not isinstance(branch, dict) or set(branch) != {'offset', 'target'} or any(type(branch[k]) is not int or not 0 <= branch[k] < 65536 for k in ('offset', 'target')):
                            raise ValueError('invalid branch')
                    for region in regions:
                        keys = {'kind', 'tryOffset', 'tryLength', 'handlerOffset', 'handlerLength'}
                        if not isinstance(region, dict) or set(region) != keys or region['kind'] not in ('Catch', 'Filter', 'Finally', 'Fault') or any(type(region[k]) is not int or not 0 <= region[k] <= 65536 for k in keys - {'kind'}):
                            raise ValueError('invalid exception region')
                    callsites = item.get('calls')
                    if not isinstance(callsites, list) or len(callsites) > 4096: raise ValueError('invalid calls')
                    safe_edges = []
                    for call in callsites:
                        if not isinstance(call, dict) or set(call) != {'offset', 'kind', 'target'} or type(call.get('offset')) is not int or not 0 <= call['offset'] < 65536 or call.get('kind') not in ('call', 'callvirt', 'newobj'):
                            raise ValueError('invalid call')
                        edge = allowed_edges.get(call.get('target'))
                        if edge: safe_edges.append({'typeId': edge[0], 'methodId': edge[1], 'kind': call['kind'], 'offset': call['offset']})
                    signatures.append(signature); edges.extend(safe_edges)
                    overloads.append({'signature': signature, 'calls': safe_edges})
                except (ValueError, TypeError):
                    unreadable = True
                    token = item.get('token') if isinstance(item, dict) else None
                    if type(token) is int and 0x06000001 <= token <= 0x06ffffff: unreadable_tokens.append(token)
            if unreadable: complete = False
            methods.append({'name': name, 'status': 'unreadable' if unreadable else 'found' if signatures else 'missing',
                            'signatures': signatures, 'calls': edges, 'overloads': overloads, 'unreadableTokens': unreadable_tokens})
        if len(target['methods']) != len(names): complete = False
        rows.append({'id': target_id, 'status': 'found' if target['found'] else 'missing', 'methods': methods})
    return {**identity, 'schemaVersion': 1, 'adapterId': 'rimworld-1.7.4985-rev1269', 'binaryVerified': binary,
            'verified': binary, 'staticAuditStatus': 'completed' if complete else 'incomplete', 'c0Passed': False, 'memoryHard': False, 'types': rows}


def publish(root):
    identity = pv.current_identity()
    raw = {}; manifest = None
    try:
        manifest = load_session(root)
        path = session_path(root) / 'scan.json'
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4*1024*1024:
            raise ValueError('invalid scanner evidence')
        raw = pv.read_json(path)
    except (ValueError, OSError):
        raw = {}
    summary = public_summary(raw, identity)
    if manifest is not None:
        summary['binaryVerified'] = True
        inputs = manifest['inputs']
        seconds = manifest.get('seconds')
        seconds = seconds if type(seconds) in (int, float) and math.isfinite(seconds) and 0 <= seconds <= 1200 else None
        summary['acquisition'] = {'files': len(inputs), 'bytes': sum(x['size'] for x in inputs.values()),
            'downloadedBytes': sum(x['size'] for x in inputs.values() if x['source'] == 'r2'),
            'reusedBytes': sum(x['size'] for x in inputs.values() if x['source'] == 'snapshot'), 'seconds': seconds}
    return summary


def serialize_summary(summary, identity):
    try:
        text = json.dumps(summary, allow_nan=False)
        if len(text.encode('utf-8')) <= 512*1024: return text
    except (ValueError, TypeError, RecursionError):
        pass
    return json.dumps({**identity, 'schemaVersion': 1, 'adapterId': 'rimworld-1.7.4985-rev1269',
                       'binaryVerified': summary.get('binaryVerified') is True if isinstance(summary, dict) else False,
                       'staticAuditStatus': 'incomplete', 'c0Passed': False, 'memoryHard': False, 'budgetExceeded': True, 'types': []})


def main():
    import argparse
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'scan', 'publish'))
    parser.add_argument('--private-root', required=True)
    parser.add_argument('--scanner')
    args = parser.parse_args()
    pv.install_stop_handlers()
    if args.action == 'prepare': prepare(Path(args.private_root))
    elif args.action == 'scan':
        if not args.scanner: raise ValueError('scanner required')
        scan(Path(args.private_root), Path(args.scanner).resolve())
    else:
        summary = publish(Path(args.private_root))
        text = serialize_summary(summary, pv.current_identity())
        print(text)
        output = os.environ.get('GITHUB_STEP_SUMMARY')
        if output:
            with open(output, 'a', encoding='utf-8') as stream:
                stream.write('## Private C static audit\n\n```json\n' + text + '\n```\n')


if __name__ == '__main__':
    main()
