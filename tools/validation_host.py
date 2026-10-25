"""Controller for the test-only RimWorld MOD validation host.

The Controller never starts the official game executable. It prepares a private,
read-only snapshot of the user's game files, builds a throwaway run directory per
case, starts the self-made Worker (worker/RimWorldValidation.Worker) under limits,
and turns the Worker's observations into a modValidationResult
(docs/contracts/mod-validation-v1.md).

Exit codes of ``run``: 0 passed, 1 failed, 2 blocked, 3 incomplete.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform as platform_module
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

TOOL_VERSION = '0.1.0'
WORKER_NAME = 'RimWorldValidationWorker'
EXIT_CODES = {'passed': 0, 'failed': 1, 'blocked': 2, 'incomplete': 3}
LEVELS = ('A', 'B', 'C')
OFFICIAL_ORDER = ('Core', 'Royalty', 'Ideology', 'Biotech', 'Anomaly', 'Odyssey')
EXPANSION_IDS = tuple(f'ludeon.rimworld.{name.lower()}' for name in OFFICIAL_ORDER[1:])
GAME_EXCLUDED = {'RimWorld', 'RimWorld.exe', 'RimWorld.deps.json', 'RimWorld.runtimeconfig.json', 'Data'}
REQUIRED_GAME_FILES = (
    'Version.txt', 'Assembly-CSharp.dll', 'RimWorld.dll', 'Waylith.dll', 'Waylith.UnityCompat.dll',
    'UnityStubs.dll', 'RimWorld.runtimeconfig.json', 'RimWorld.deps.json', 'Assets.zip',
    'libhostfxr.so', 'libcoreclr.so', 'System.Private.CoreLib.dll', 'Data/Core/About/About.xml',
)
# Files whose content decides which adapter applies; re-hashed on every run.
IDENTITY_FILES = (
    'Version.txt', 'Assembly-CSharp.dll', 'RimWorld.dll', 'Waylith.dll', 'Waylith.UnityCompat.dll',
    'UnityStubs.dll', 'RimWorld.runtimeconfig.json', 'RimWorld.deps.json', 'libcoreclr.so',
    'System.Private.CoreLib.dll',
)

# Builds the Worker has been checked against. ``qualifiedLevels`` is only granted
# for the platform/runtime pair that was compared with the official headless boot
# (docs/research/test-host-qualification.md); anything else runs as experimental.
ADAPTERS = {
    'rimworld-1.7.4985-rev1269': {
        'version': '1.7.4985 rev1269',
        'sha256': {
            'Assembly-CSharp.dll': '0be7a7ea4b3111d4430f45b36c234a5e43287880b0514b23915f2ef9a0629e16',
            'RimWorld.dll': '39bd67253a7fa5503ff7f2b51bc3ab5983fb1430acf57d7e8bb322d20e380555',
            'Waylith.dll': 'c69c2a2828c5594b58c9b28f0d19d5b25ff5cb16ceb46dc64f34dd59b7affc26',
            'UnityStubs.dll': 'ea962c9274514e0633d4e4c5471a1a98aff5fc52af20ca2e506c16dcd8be6f81',
            'Waylith.UnityCompat.dll': 'de9bcdb4399caac13435840b007994d054d4ffce9b0081ae5fcd3eb1479c10e0',
        },
        'qualified': {
            ('linux-x64', 'waylith'): {
                'levels': ('A', 'B'),
                'runtimeSha256': {
                    'libcoreclr.so': 'eef17620f564c69d67ad9dcdef241902e9c12fef1cd090c973ab12a551f603d3',
                    'System.Private.CoreLib.dll': 'd2075bc8fd8e2f0b4780ec248034b30e33d4cdd72513730886c5989d1f8008b7',
                },
                'evidence': 'docs/research/test-host-qualification.md#linux-x64-waylithclr',
            },
        },
    },
}

DEFAULT_LIMITS = {'timeoutSeconds': 180, 'memoryMiB': 4096, 'logMiB': 32, 'diagnostics': 2000, 'messageKiB': 16}
LIMIT_RANGES = {
    'timeoutSeconds': (10, 3600), 'memoryMiB': (512, 65536), 'logMiB': (1, 1024),
    'diagnostics': (10, 100000), 'messageKiB': (1, 1024),
}
MAX_MOD_BYTES = 4 * 1024 ** 3
MAX_REQUEST_BYTES = 1024 ** 2
SAFE_LANGUAGE = re.compile(r'[^\x00-\x1f/\\:*?"<>|]{1,64}')


class RequestError(ValueError):
    """The request cannot be accepted; reported as status=blocked."""


class Blocked(Exception):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------------------
# Hashing and snapshots

def sha256_file(path, chunk=1024 * 1024):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        while block := stream.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def _walk_files(root):
    """Regular files under root, relative POSIX paths, sorted. Symlinks are returned separately."""
    files, links = [], []
    for current, dirs, names in os.walk(root):
        dirs.sort()
        for name in list(dirs):
            full = Path(current) / name
            if full.is_symlink():
                links.append(full.relative_to(root).as_posix())
                dirs.remove(name)
        for name in sorted(names):
            full = Path(current) / name
            rel = full.relative_to(root).as_posix()
            if full.is_symlink():
                links.append(rel)
            elif full.is_file():
                files.append(rel)
    return files, links


def prepare_game(source, snapshot, *, log=print):
    """Copy the user's game folder into a private read-only snapshot with a SHA-256 manifest."""
    source = Path(source).resolve()
    snapshot = Path(snapshot).resolve()
    missing = [name for name in REQUIRED_GAME_FILES if not (source / name).is_file()]
    if missing:
        raise Blocked('missingGameFiles', 'game folder lacks required files: ' + ', '.join(missing))
    if snapshot.exists():
        raise Blocked('snapshotExists', f'{snapshot} already exists; choose a new snapshot directory')
    if snapshot == source or source in snapshot.parents:
        raise Blocked('snapshotInsideSource', 'the snapshot must not be inside the game folder')
    started = time.monotonic()
    game = snapshot / 'game'
    snapshot.mkdir(parents=True)
    shutil.copytree(source, game, symlinks=True)
    copied = time.monotonic()
    files, links = _walk_files(game)
    manifest = {}
    for rel in files:
        path = game / rel
        manifest[rel] = {'size': path.stat().st_size, 'sha256': sha256_file(path)}
    hashed = time.monotonic()
    for rel in files:
        path = game / rel
        mode = path.stat().st_mode
        path.chmod(stat.S_IMODE(mode) & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    for current, dirs, _ in os.walk(game, topdown=False):
        Path(current).chmod(0o555)
    info = {
        'recordType': 'rwmtGameSnapshot', 'schemaVersion': 1,
        'createdAt': _now(), 'sourcePath': str(source),
        'version': (game / 'Version.txt').read_text(encoding='utf-8').strip(),
        'officialContent': _official_folders(game),
        'fileCount': len(manifest), 'totalBytes': sum(e['size'] for e in manifest.values()),
        'symlinks': links,
        'fingerprint': _fingerprint(manifest),
        'adapter': match_adapter(manifest)[0],
        'timings': {'copySeconds': round(copied - started, 3), 'hashSeconds': round(hashed - copied, 3),
                    'totalSeconds': round(time.monotonic() - started, 3)},
        'files': manifest,
    }
    _write_json(snapshot / 'snapshot.json', info)
    (snapshot / 'snapshot.json').chmod(0o444)
    log(json.dumps({k: v for k, v in info.items() if k != 'files'}, ensure_ascii=False, indent=2))
    return info


def _official_folders(game):
    data = game / 'Data'
    return [name for name in OFFICIAL_ORDER if (data / name / 'About' / 'About.xml').is_file()]


def _fingerprint(manifest):
    digest = hashlib.sha256()
    for rel in IDENTITY_FILES:
        entry = manifest.get(rel)
        digest.update(f'{rel}\0{entry["sha256"] if entry else "-"}\n'.encode())
    return digest.hexdigest()


def match_adapter(manifest, adapters=None):
    adapters = ADAPTERS if adapters is None else adapters
    for name, adapter in adapters.items():
        if all(manifest.get(rel, {}).get('sha256') == value for rel, value in adapter['sha256'].items()):
            return name, adapter
    return None, None


def load_snapshot(snapshot, *, full=False, official=()):
    """Verify a prepared snapshot. Identity files are always re-hashed; ``full`` re-hashes everything."""
    snapshot = Path(snapshot).resolve()
    info_path = snapshot / 'snapshot.json'
    if not info_path.is_file():
        raise Blocked('snapshotMissing', f'{info_path} not found; run prepare-game first')
    info = json.loads(info_path.read_text(encoding='utf-8'))
    if info.get('recordType') != 'rwmtGameSnapshot' or info.get('schemaVersion') != 1:
        raise Blocked('snapshotInvalid', 'unsupported snapshot record')
    game = snapshot / 'game'
    manifest = info['files']
    problems = []
    for rel, entry in manifest.items():
        path = game / rel
        try:
            if path.is_symlink() or path.stat().st_size != entry['size']:
                problems.append(rel)
        except FileNotFoundError:
            problems.append(rel)
    for rel in (manifest if full else [r for r in IDENTITY_FILES if r in manifest]):
        if rel not in problems and sha256_file(game / rel) != manifest[rel]['sha256']:
            problems.append(rel)
    for folder in official:
        files, links = _walk_files(game / 'Data' / folder)
        extra = [f'Data/{folder}/{f}' for f in files if f'Data/{folder}/{f}' not in manifest] + links
        problems.extend(extra)
    if problems:
        raise Blocked('snapshotModified', 'snapshot differs from its manifest: ' + ', '.join(sorted(problems)[:20]))
    info['verification'] = 'full' if full else 'sizes+identityHashes'
    info['path'] = str(snapshot)
    return info


# ---------------------------------------------------------------------------
# Request

REQUEST_KEYS = {'recordType', 'schemaVersion', 'levels', 'official', 'mods', 'language', 'expectations', 'limits', 'tests'}
MOD_KEYS = {'path', 'packageId', 'target'}
EXPECTATION_KEYS = {
    'defs': ({'type', 'defName', 'exists'}, set()),
    'defValues': ({'type', 'defName', 'path', 'equals'}, set()),
    'keyed': ({'key'}, {'equals'}),
    'harmonyPatches': ({'owner', 'targetAssembly', 'targetType', 'targetMethod', 'targetParameters',
                        'kind', 'patchType', 'patchMethod'}, {'genericArity'}),
}
PATCH_KINDS = {'prefix', 'postfix', 'transpiler', 'finalizer'}


def load_request(path):
    path = Path(path).resolve()
    if path.stat().st_size > MAX_REQUEST_BYTES:
        raise RequestError('request exceeds 1 MiB')
    raw = path.read_bytes()
    try:
        request = json.loads(raw.decode('utf-8-sig'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RequestError(f'request is not valid JSON: {error}') from None
    validated = validate_request(request, path.parent)
    validated['sha256'] = hashlib.sha256(raw).hexdigest()
    return validated


def _require(condition, message):
    if not condition:
        raise RequestError(message)


def _strings(value, name, allow_empty=False):
    _require(isinstance(value, list) and (allow_empty or value) and all(isinstance(v, str) and v for v in value),
             f'{name} must be a {"" if allow_empty else "nonempty "}array of nonempty strings')
    return value


def validate_request(request, base):
    _require(isinstance(request, dict), 'request must be a JSON object')
    unknown = set(request) - REQUEST_KEYS
    _require(not unknown, f'unknown request fields: {", ".join(sorted(unknown))}')
    _require(request.get('recordType') == 'modValidationRequest', 'recordType must be modValidationRequest')
    _require(request.get('schemaVersion') == 1, 'schemaVersion must be 1')

    levels = _strings(request.get('levels'), 'levels')
    _require(len(set(levels)) == len(levels) and set(levels) <= set(LEVELS), 'levels must be distinct values of A, B, C')
    _require('A' in levels, 'levels must include A; B and C depend on a completed load')

    official = _strings(request.get('official', ['Core']), 'official')
    _require(official[0] == 'Core', 'official must start with Core')
    _require(len(set(official)) == len(official) and set(official) <= set(OFFICIAL_ORDER),
             f'official entries must be distinct values of {", ".join(OFFICIAL_ORDER)}')

    mods = request.get('mods')
    _require(isinstance(mods, list) and mods, 'mods must be a nonempty array')
    resolved = []
    for index, mod in enumerate(mods):
        _require(isinstance(mod, dict), f'mods[{index}] must be an object')
        unknown = set(mod) - MOD_KEYS
        _require(not unknown, f'mods[{index}] has unknown fields: {", ".join(sorted(unknown))}')
        _require(isinstance(mod.get('path'), str) and mod['path'], f'mods[{index}].path must be a nonempty string')
        _require(isinstance(mod.get('target', False), bool), f'mods[{index}].target must be a boolean')
        if 'packageId' in mod:
            _require(isinstance(mod['packageId'], str) and mod['packageId'], f'mods[{index}].packageId must be a string')
        resolved.append({'path': str((base / mod['path']).resolve()), 'packageId': mod.get('packageId'),
                         'target': mod.get('target', False)})
    _require(any(m['target'] for m in resolved), 'at least one mod must have "target": true')

    language = request.get('language', 'English')
    _require(isinstance(language, str) and SAFE_LANGUAGE.fullmatch(language) and language.strip('. ') == language,
             'language must be a language folder name')

    expectations = request.get('expectations', {})
    _require(isinstance(expectations, dict), 'expectations must be an object')
    unknown = set(expectations) - set(EXPECTATION_KEYS)
    _require(not unknown, f'unknown expectation kinds: {", ".join(sorted(unknown))}')
    for kind, items in expectations.items():
        required, optional = EXPECTATION_KEYS[kind]
        _require(isinstance(items, list), f'expectations.{kind} must be an array')
        for index, item in enumerate(items):
            where = f'expectations.{kind}[{index}]'
            _require(isinstance(item, dict), f'{where} must be an object')
            _require(required <= set(item) <= required | optional,
                     f'{where} needs exactly {", ".join(sorted(required))}' + (f' (optional {", ".join(sorted(optional))})' if optional else ''))
            for key, value in item.items():
                if key == 'exists':
                    _require(isinstance(value, bool), f'{where}.exists must be a boolean')
                elif key == 'genericArity':
                    _require(isinstance(value, int) and not isinstance(value, bool) and value >= 0, f'{where}.genericArity must be >= 0')
                elif key == 'targetParameters':
                    _strings(value, f'{where}.targetParameters', allow_empty=True)
                else:
                    _require(isinstance(value, str) and value, f'{where}.{key} must be a nonempty string')
            if kind == 'harmonyPatches':
                _require(item['kind'] in PATCH_KINDS, f'{where}.kind must be one of {", ".join(sorted(PATCH_KINDS))}')
    if expectations.get('harmonyPatches'):
        _require('B' in levels, 'harmonyPatches expectations need level B')

    tests = request.get('tests', [])
    _require(isinstance(tests, list), 'tests must be an array')
    if 'C' in levels:
        _strings(tests, 'tests')
    else:
        _require(not tests, 'tests need level C')

    limits = dict(DEFAULT_LIMITS)
    given = request.get('limits', {})
    _require(isinstance(given, dict), 'limits must be an object')
    for key, value in given.items():
        _require(key in LIMIT_RANGES, f'unknown limit {key}')
        low, high = LIMIT_RANGES[key]
        _require(isinstance(value, int) and not isinstance(value, bool) and low <= value <= high,
                 f'limits.{key} must be an integer in [{low}, {high}]')
        limits[key] = value
    return {'levels': levels, 'official': official, 'mods': resolved, 'language': language,
            'expectations': {k: expectations.get(k, []) for k in EXPECTATION_KEYS}, 'tests': tests, 'limits': limits}


def resolve_language(game, language):
    """Map a request language to the Core language folder/archive name the game uses.

    Exact names win; otherwise the English part before " (" is accepted when it is
    unique, e.g. "Japanese" -> "Japanese (日本語)" (shipped as Japanese (日本語).tar).
    """
    languages = Path(game) / 'Data' / 'Core' / 'Languages'
    names = sorted({p.name[:-4] if p.name.endswith('.tar') else p.name for p in languages.iterdir()
                    if p.is_dir() or p.name.endswith('.tar')}) if languages.is_dir() else []
    if language in names:
        return language
    matches = [n for n in names if n.split(' (', 1)[0] == language]
    if len(matches) == 1:
        return matches[0]
    raise Blocked('languageMissing', f'language {language!r} not found in Core/Languages; available: {", ".join(names)}')


def _about_package_id(mod_dir):
    about = Path(mod_dir) / 'About' / 'About.xml'
    if not about.is_file():
        raise Blocked('modInvalid', f'{mod_dir} has no About/About.xml')
    try:
        root = ET.fromstring(about.read_bytes())
    except ET.ParseError as error:
        raise Blocked('modInvalid', f'{about}: {error}') from None
    package_id = (root.findtext('packageId') or '').strip()
    if not package_id:
        raise Blocked('modInvalid', f'{about} has no packageId')
    return package_id.lower()


def _tree_files(root):
    files, links = _walk_files(root)
    files = [f for f in files if not f.startswith('.git/') and '/.git/' not in f]
    return files, [l for l in links if not l.startswith('.git')]


def inspect_mods(request):
    """Resolve mod folders, packageIds and content hashes before anything starts."""
    mods, folders, ids, total = [], set(), set(), 0
    for mod in request['mods']:
        root = Path(mod['path'])
        if not root.is_dir():
            raise Blocked('modMissing', f'mod folder not found: {root}')
        package_id = _about_package_id(root)
        if mod['packageId'] and mod['packageId'].lower() != package_id:
            raise Blocked('modMismatch', f'{root}: About.xml packageId is {package_id}, request says {mod["packageId"]}')
        if package_id.startswith('ludeon.'):
            raise Blocked('modInvalid', f'{root}: official content is selected with "official", not "mods"')
        if package_id in ids or root.name in folders:
            raise Blocked('modDuplicate', f'duplicate mod {package_id} / folder {root.name}')
        files, links = _tree_files(root)
        if links:
            raise Blocked('modInvalid', f'{root} contains symbolic links: {", ".join(links[:5])}')
        digest, size, entries = hashlib.sha256(), 0, {}
        for rel in files:
            file_hash = sha256_file(root / rel)
            entries[rel] = file_hash
            size += (root / rel).stat().st_size
            digest.update(f'{rel}\0{file_hash}\n'.encode())
        total += size
        if total > MAX_MOD_BYTES:
            raise Blocked('modTooLarge', 'mods exceed 4 GiB in total')
        ids.add(package_id)
        folders.add(root.name)
        mods.append({'packageId': package_id, 'target': mod['target'], 'sourcePath': str(root), 'folderName': root.name,
                     'files': len(files), 'bytes': size, 'sha256': digest.hexdigest(), 'fileHashes': entries,
                     'harmonyAssemblies': sorted(rel for rel in files if rel.lower().endswith('/0harmony.dll'))})
    return mods


# ---------------------------------------------------------------------------
# Run directories

def current_platform():
    system = {'Linux': 'linux', 'Windows': 'windows', 'Darwin': 'osx'}.get(platform_module.system(), platform_module.system().lower())
    machine = platform_module.machine().lower()
    arch = {'x86_64': 'x64', 'amd64': 'x64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(machine, machine)
    return f'{system}-{arch}'


def _official_package_id(game, folder):
    return _about_package_id(game / 'Data' / folder)


def build_run_dir(run_dir, snapshot, request, mods, worker_dir, runtime, *, expectations, run_id, nonce, deadline):
    """Create host/ (symlinks to the read-only snapshot + copied mods + Worker) and userdata/."""
    game = Path(snapshot['path']) / 'game'
    host = run_dir / 'host'
    userdata = run_dir / 'userdata'
    for sub in (host / 'Data', host / 'Mods', userdata / 'Config', userdata / 'logs', userdata / 'tmp',
                run_dir / 'home', run_dir / 'tmp'):
        sub.mkdir(parents=True)

    runtime_pack = set()
    deps = json.loads((game / 'RimWorld.deps.json').read_text(encoding='utf-8'))
    target_name = deps['runtimeTarget']['name']
    targets = deps['targets'][target_name]
    if runtime == 'standard':
        for key, value in targets.items():
            if key.startswith('runtimepack.'):
                for section in ('runtime', 'native'):
                    runtime_pack.update(Path(f).name for f in value.get(section, {}))
    for name in sorted(os.listdir(game)):
        if name in GAME_EXCLUDED or name in runtime_pack:
            continue
        os.symlink(game / name, host / name)
    for folder in request['official']:
        os.symlink(game / 'Data' / folder, host / 'Data' / folder)
    for mod in mods:
        destination = host / 'Mods' / mod['folderName']
        source = Path(mod['sourcePath'])
        destination.mkdir()
        for rel in mod['fileHashes']:
            (destination / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / rel, destination / rel)
            if sha256_file(destination / rel) != mod['fileHashes'][rel]:
                raise Blocked('modChanged', f'{source / rel} changed while it was being copied')

    for suffix in ('', '.dll', '.exe'):
        if (worker_dir / (WORKER_NAME + suffix)).is_file():
            shutil.copy2(worker_dir / (WORKER_NAME + suffix), host / (WORKER_NAME + suffix))
    if runtime == 'waylith':
        shutil.copyfile(game / 'RimWorld.runtimeconfig.json', host / f'{WORKER_NAME}.runtimeconfig.json')
        root_key = next(k for k in targets if k.startswith('RimWorld/'))
        root = targets.pop(root_key)
        root['runtime'] = {f'{WORKER_NAME}.dll': {}}
        deps['targets'][target_name] = {f'{WORKER_NAME}/{TOOL_VERSION}': root, **targets}
        libraries = deps['libraries']
        library = libraries.pop(root_key)
        deps['libraries'] = {f'{WORKER_NAME}/{TOOL_VERSION}': library, **libraries}
        _write_json(host / f'{WORKER_NAME}.deps.json', deps)
    else:
        source = json.loads((game / 'RimWorld.runtimeconfig.json').read_text(encoding='utf-8'))
        properties = {k: v for k, v in source['runtimeOptions'].get('configProperties', {}).items()
                      if not k.startswith('WaylithClr.')}
        _write_json(host / f'{WORKER_NAME}.runtimeconfig.json', {'runtimeOptions': {
            'tfm': 'net10.0', 'framework': {'name': 'Microsoft.NETCore.App', 'version': '10.0.0'},
            'rollForward': 'LatestPatch', 'configProperties': properties}})

    official_ids = [_official_package_id(game, folder) for folder in request['official']]
    order = official_ids + [m['packageId'] for m in mods]
    version = snapshot['version']
    active = ''.join(f'<li>{_xml_text(i)}</li>' for i in order)
    known = ''.join(f'<li>{i}</li>' for i in EXPANSION_IDS)
    (userdata / 'Config' / 'ModsConfig.xml').write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<ModsConfigData>'
        f'<version>{_xml_text(version)}</version><activeMods>{active}</activeMods>'
        f'<knownExpansions>{known}</knownExpansions></ModsConfigData>\n', encoding='utf-8')
    (userdata / 'Config' / 'Prefs.xml').write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<PrefsData><devMode>true</devMode>'
        '<resetModsConfigOnCrash>false</resetModsConfigOnCrash>'
        f'<langFolderName>{_xml_text(request["language"])}</langFolderName></PrefsData>\n', encoding='utf-8')

    limits = request['limits']
    log_bytes = limits['logMiB'] * 1024 * 1024
    worker_request = {
        'recordType': 'rwmtWorkerRequest', 'schemaVersion': 1, 'runId': run_id, 'nonce': nonce,
        'hostDir': str(host), 'userDataDir': str(userdata),
        'eventsPath': str(run_dir / 'events.jsonl'), 'resultPath': str(run_dir / 'worker-result.json'),
        'language': request['language'],
        'limits': {'deadlineSeconds': deadline, 'diagnostics': limits['diagnostics'],
                   'messageBytes': limits['messageKiB'] * 1024, 'eventBytes': log_bytes // 2},
        'expectedModOrder': order, 'expectations': expectations,
    }
    _write_json(run_dir / 'worker-request.json', worker_request)
    return order


def _xml_text(value):
    return value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


# ---------------------------------------------------------------------------
# Process supervision (Linux)

def _process_group_rss(pgid):
    total = 0
    for entry in os.scandir('/proc'):
        if not entry.name.isdigit():
            continue
        try:
            with open(f'/proc/{entry.name}/stat', 'rb') as stream:
                fields = stream.read().rsplit(b')', 1)[1].split()
            if int(fields[2]) != pgid:
                continue
            with open(f'/proc/{entry.name}/statm', 'rb') as stream:
                total += int(stream.read().split()[1]) * os.sysconf('SC_PAGE_SIZE')
        except (OSError, IndexError, ValueError):
            continue
    return total


def _group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _dir_bytes(paths):
    total = 0
    for path in paths:
        if path.is_file():
            total += path.stat().st_size
        elif path.is_dir():
            for current, _, names in os.walk(path):
                for name in names:
                    try:
                        total += (Path(current) / name).stat().st_size
                    except OSError:
                        pass
    return total


def supervise(run_dir, limits, environment, *, poll=0.2):
    """Start the Worker in its own process group and enforce time, memory and log limits."""
    host = run_dir / 'host'
    command = [str(host / WORKER_NAME), '--worker-request', str(run_dir / 'worker-request.json')]
    memory_limit = limits['memoryMiB'] * 1024 * 1024
    log_limit = limits['logMiB'] * 1024 * 1024
    log_paths = [run_dir / 'stdout.log', run_dir / 'stderr.log', run_dir / 'events.jsonl', run_dir / 'userdata' / 'logs']
    started = time.monotonic()
    with open(run_dir / 'stdout.log', 'wb') as out, open(run_dir / 'stderr.log', 'wb') as err:
        process = subprocess.Popen(command, cwd=host, env=environment, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                   start_new_session=True)
    pgid = process.pid
    peak, killed, return_code = 0, None, None
    while True:
        return_code = process.poll()
        if return_code is not None:
            break
        elapsed = time.monotonic() - started
        rss = _process_group_rss(pgid)
        peak = max(peak, rss)
        if elapsed > limits['timeoutSeconds']:
            killed = 'timeout'
        elif rss > memory_limit:
            killed = 'memoryLimit'
        elif _dir_bytes(log_paths) > log_limit:
            killed = 'logLimit'
        if killed:
            os.killpg(pgid, signal.SIGKILL)
            return_code = process.wait()
            break
        time.sleep(poll)
    # The Worker exits with Environment.Exit; anything left in its group is a stray descendant.
    stray = _group_alive(pgid)
    if stray:
        os.killpg(pgid, signal.SIGKILL)
    return {
        'command': [Path(command[0]).name, *command[1:2]], 'exitCode': return_code, 'killedFor': killed,
        'strayProcessesKilled': stray, 'seconds': round(time.monotonic() - started, 3), 'peakRssBytes': peak,
        'logBytes': _dir_bytes(log_paths),
        'enforcement': {'timeout': 'SIGKILL to process group', 'memory': 'polled group RSS + DOTNET_GCHeapHardLimit',
                        'memoryHard': False, 'logs': 'polled size', 'pollSeconds': poll},
    }


def worker_environment(run_dir, limits, runtime):
    env = {
        'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
        'HOME': str(run_dir / 'home'), 'TMPDIR': str(run_dir / 'tmp'),
        'XDG_CONFIG_HOME': str(run_dir / 'home' / '.config'), 'XDG_DATA_HOME': str(run_dir / 'home' / '.local' / 'share'),
        'XDG_CACHE_HOME': str(run_dir / 'home' / '.cache'), 'LANG': 'C.UTF-8',
        'DOTNET_CLI_TELEMETRY_OPTOUT': '1', 'DOTNET_NOLOGO': '1',
        'DOTNET_GCHeapHardLimit': format(limits['memoryMiB'] * 1024 * 1024, 'x'),
    }
    if runtime == 'standard' and os.environ.get('DOTNET_ROOT'):
        env['DOTNET_ROOT'] = os.environ['DOTNET_ROOT']
    return env


def read_worker_output(run_dir, run_id, nonce, started_wall, max_events):
    """Return (result or None, problem or None, events)."""
    result_path = run_dir / 'worker-result.json'
    events = []
    events_path = run_dir / 'events.jsonl'
    if events_path.is_file():
        with open(events_path, encoding='utf-8', errors='replace') as stream:
            for line in stream:
                if len(events) >= max_events:
                    break
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    events.append({'level': 'error', 'category': 'Controller', 'message': 'unreadable event line', 'stage': None})
    if not result_path.is_file():
        return None, 'workerResultMissing', events
    try:
        result = json.loads(result_path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, 'workerResultUnreadable', events
    if result.get('recordType') != 'rwmtWorkerResult' or result.get('schemaVersion') != 1:
        return None, 'workerResultInvalid', events
    if result.get('runId') != run_id or result.get('nonce') != nonce or result_path.stat().st_mtime < started_wall - 1:
        return None, 'workerResultStale', events
    return result, None, events


# ---------------------------------------------------------------------------
# Evaluation

def _event_key(event):
    return (event.get('level'), event.get('category'), event.get('message'))


def new_diagnostics(target_events, baseline_events):
    """Errors/warnings present in the target run but not in the baseline (multiset difference)."""
    remaining = {}
    for event in baseline_events:
        if event.get('level') in ('error', 'warning'):
            remaining[_event_key(event)] = remaining.get(_event_key(event), 0) + 1
    fresh = []
    for event in target_events:
        if event.get('level') not in ('error', 'warning'):
            continue
        key = _event_key(event)
        if remaining.get(key):
            remaining[key] -= 1
        else:
            fresh.append(event)
    return fresh


def _mentions(event, mods):
    text = (event.get('message') or '').lower()
    return sorted({m['packageId'] for m in mods if m['target'] and (m['packageId'] in text or m['folderName'].lower() in text)})


def evaluate(request, mods, worker, worker_problem, events, baseline, baseline_problem, baseline_events, process,
             fidelity, *, language_check=True):
    """Apply the status rules of docs/contracts/mod-validation-v1.md. Returns (status, executionStatus, reasons, stages)."""
    incomplete, failed = [], []
    levels = request['levels']
    stages = {level: {'status': 'notRequested'} for level in LEVELS}

    if process.get('killedFor'):
        incomplete.append({'code': process['killedFor'], 'detail': f'Worker stopped by the Controller ({process["killedFor"]})'})
    if worker_problem:
        incomplete.append({'code': worker_problem, 'detail': 'no valid result from this run of the Worker'})
    execution = 'interrupted' if process.get('killedFor') else 'failed'
    if worker:
        execution = {'completed': 'completed', 'interrupted': 'interrupted'}.get(worker.get('executionStatus'), 'failed')
        if worker.get('executionStatus') != 'completed':
            incomplete.append({'code': f'worker{worker.get("executionStatus", "unknown").capitalize()}',
                               'detail': worker.get('failure') or 'the Worker did not complete'})
        if process.get('exitCode') not in (0, None) and worker.get('executionStatus') == 'completed':
            incomplete.append({'code': 'workerExitCode', 'detail': f'Worker exit code {process.get("exitCode")} after a completed result'})
    if baseline_problem:
        incomplete.append({'code': 'baselineIncomplete', 'detail': baseline_problem})
    if fidelity != 'qualified':
        incomplete.append({'code': 'experimental', 'detail': 'this platform/runtime/build is not qualified; results cannot prove game compatibility'})

    completed = worker is not None and worker.get('executionStatus') == 'completed'
    if completed:
        summary = worker.get('diagnosticsSummary', {})
        if summary.get('dropped'):
            incomplete.append({'code': 'diagnosticsDropped', 'detail': f'{summary["dropped"]} diagnostics were dropped at the limit'})
        if worker.get('verseLogLimitReached'):
            incomplete.append({'code': 'verseLogLimit', 'detail': 'the game stopped logging after its message limit'})
        order = worker.get('modOrder')
        if not order or not order.get('matches'):
            incomplete.append({'code': 'modOrderMismatch', 'detail': 'the mods that actually loaded differ from the request',
                               'expected': (order or {}).get('expected'), 'actual': (order or {}).get('actual')})
        if language_check and worker.get('activeLanguage') != request['language']:
            incomplete.append({'code': 'languageNotApplied',
                               'detail': f'active language is {worker.get("activeLanguage")}, requested {request["language"]}'})
        if worker.get('loadException'):
            failed.append({'code': 'loadException', 'detail': worker['loadException'].splitlines()[0]})
        if not worker.get('playDataLoaded'):
            failed.append({'code': 'playDataNotLoaded', 'detail': 'PlayDataLoader did not report Loaded'})
        for key in ('runningModsError', 'modOrderError', 'checksError', 'activeLanguageError'):
            if worker.get(key):
                incomplete.append({'code': key, 'detail': worker[key].splitlines()[0]})

    checks = (worker or {}).get('checks') if completed else None
    a_results = []
    if checks is not None:
        a_results = checks.get('defs', []) + checks.get('defValues', []) + checks.get('keyed', [])
    stage_a = {'status': 'incomplete', 'checks': len(a_results)}
    if completed and checks is not None:
        bad = [c for c in a_results if c.get('outcome') == 'mismatch']
        errors = [c for c in a_results if c.get('outcome') not in ('match', 'mismatch')]
        if errors:
            incomplete.append({'code': 'checkError', 'detail': f'{len(errors)} level A expectations could not be evaluated'})
        if bad:
            failed.append({'code': 'expectationMismatch', 'detail': f'{len(bad)} level A expectations did not match'})
        stage_a['status'] = 'incomplete' if errors else 'failed' if bad else 'completed'
    elif completed and worker.get('playDataLoaded') is False:
        stage_a['status'] = 'failed'
    stages['A'] = stage_a

    if 'B' in levels:
        expected = request['expectations']['harmonyPatches']
        stage_b = {'status': 'incomplete', 'expectedPatches': len(expected)}
        harmony = (checks or {}).get('harmony') if checks is not None else None
        if not expected:
            incomplete.append({'code': 'noExpectedPatches', 'detail': 'level B needs fully specified expected Harmony patches'})
        elif harmony is not None:
            outcomes = [p.get('outcome') for p in harmony.get('expected', [])]
            if 'error' in outcomes or harmony.get('registryError'):
                incomplete.append({'code': 'harmonyCheckError', 'detail': 'some expected patches could not be resolved'})
                stage_b['status'] = 'incomplete'
            elif 'missing' in outcomes:
                failed.append({'code': 'harmonyPatchMissing', 'detail': f'{outcomes.count("missing")} expected Harmony patches are not registered'})
                stage_b['status'] = 'failed'
            else:
                stage_b['status'] = 'completed'
            if harmony.get('unexpected'):
                stage_b['unexpectedPatches'] = len(harmony['unexpected'])
        stages['B'] = stage_b
    if 'C' in levels:
        stages['C'] = {'status': 'blocked', 'detail': 'level C tests are not implemented in this version'}

    fresh = []
    if completed and baseline is not None:
        fresh = new_diagnostics(events, baseline_events)
        errors = [e for e in fresh if e.get('level') == 'error']
        warnings = [e for e in fresh if e.get('level') == 'warning']
        if errors:
            failed.append({'code': 'newErrors', 'detail': f'{len(errors)} errors appear only when the target mods are loaded'})
        if warnings:
            failed.append({'code': 'newWarnings', 'detail': f'{len(warnings)} warnings appear only when the target mods are loaded'})
    for event in fresh:
        event['mentionsTargets'] = _mentions(event, mods)

    if incomplete:
        status = 'incomplete'
    elif failed:
        status = 'failed'
    else:
        status = 'passed'
    for level in levels:
        if stages[level]['status'] == 'completed' and status == 'incomplete':
            stages[level]['note'] = 'stage observations completed, but the run as a whole is incomplete'
    return status, execution, incomplete + failed, stages, fresh


# ---------------------------------------------------------------------------
# run

def run_validation(snapshot_dir, request_path, out_dir, worker_dir, *, runtime='waylith', baseline_cache=None,
                   allow_unknown_build=False, verify_full=False, keep_run_dirs=False, adapters=None, platform=None):
    started_wall = time.time()
    started = time.monotonic()
    out_dir = Path(out_dir).resolve()
    timings = {}
    result = {
        'recordType': 'modValidationResult', 'schemaVersion': 1,
        'tool': {'name': 'rimworld-mod-validation-host', 'version': TOOL_VERSION},
        'runId': secrets.token_hex(8), 'startedAt': _now(), 'platform': platform or current_platform(),
        'runtime': {'requested': runtime}, 'request': {'path': str(Path(request_path).resolve())},
    }
    try:
        if out_dir.exists() and any(out_dir.iterdir()):
            raise Blocked('outputNotEmpty', f'{out_dir} is not empty')
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            request = load_request(request_path)
        except (OSError, RequestError) as error:
            raise Blocked('invalidRequest', str(error)) from None
        result['request'].update({'sha256': request['sha256'], 'levels': request['levels'], 'official': request['official'],
                                  'language': request['language'], 'limits': request['limits']})
        if result['platform'] != 'linux-x64':
            raise Blocked('platformUnsupported',
                          f'running the Worker is implemented for linux-x64 only; this is {result["platform"]}')
        if runtime not in ('waylith', 'standard'):
            raise Blocked('runtimeUnsupported', f'unknown runtime {runtime}')
        if 'C' in request['levels']:
            raise Blocked('levelUnsupported', 'level C (specified behaviour tests) is not implemented in this version')
        worker_dir = Path(worker_dir).resolve()
        if not (worker_dir / WORKER_NAME).is_file() or not (worker_dir / f'{WORKER_NAME}.dll').is_file():
            raise Blocked('workerMissing', f'Worker build not found in {worker_dir}; build worker/RimWorldValidation.Worker first')
        result['tool']['workerSha256'] = sha256_file(worker_dir / f'{WORKER_NAME}.dll')

        mark = time.monotonic()
        snapshot = load_snapshot(snapshot_dir, full=verify_full, official=request['official'])
        timings['verifySnapshotSeconds'] = round(time.monotonic() - mark, 3)
        missing = [f for f in request['official'] if f not in snapshot['officialContent']]
        if missing:
            raise Blocked('officialContentMissing', 'snapshot lacks official content: ' + ', '.join(missing))
        request['language'] = resolve_language(Path(snapshot['path']) / 'game', request['language'])
        result['request']['language'] = request['language']
        adapter_name, adapter = match_adapter(snapshot['files'], adapters)
        result['game'] = {'snapshot': snapshot['path'], 'version': snapshot['version'], 'fingerprint': snapshot['fingerprint'],
                          'adapter': adapter_name, 'verification': snapshot['verification']}
        if adapter is None and not allow_unknown_build:
            raise Blocked('unknownBuild', f'no adapter for game build {snapshot["version"]}; '
                          'pass --allow-unknown-build to run it as experimental')
        qualification = (adapter or {}).get('qualified', {}).get((result['platform'], runtime))
        if qualification:
            runtime_ok = all(snapshot['files'].get(rel, {}).get('sha256') == value
                             for rel, value in qualification['runtimeSha256'].items())
            levels_ok = set(request['levels']) <= set(qualification['levels'])
            fidelity = 'qualified' if runtime_ok and levels_ok else 'experimental'
        else:
            fidelity = 'experimental'
        result['fidelity'] = fidelity
        result['qualificationEvidence'] = qualification['evidence'] if qualification and fidelity == 'qualified' else None

        mark = time.monotonic()
        mods = inspect_mods(request)
        timings['inspectModsSeconds'] = round(time.monotonic() - mark, 3)
        result['mods'] = [{k: v for k, v in m.items() if k != 'fileHashes'} for m in mods]
        if 'B' in request['levels'] and request['expectations']['harmonyPatches'] and not any(m['harmonyAssemblies'] for m in mods):
            raise Blocked('harmonyMissing', 'level B expects Harmony patches but no mod in the list ships 0Harmony.dll '
                          '(add the Harmony mod the target depends on)')
    except Blocked as blocked:
        result.update({'status': 'blocked', 'executionStatus': 'notStarted',
                       'reasons': [{'code': blocked.code, 'detail': blocked.detail}]})
        return _finish(result, out_dir, started, timings)

    limits = request['limits']
    timeout = limits['timeoutSeconds']
    # The Worker stops itself at the deadline (watchdog 2 s later); the Controller's
    # kill at the timeout is the backstop and leaves no Worker result.
    deadline = timeout - max(5.0, timeout * 0.1)
    expectations = {k: v for k, v in request['expectations'].items()}

    def one_run(name, run_mods, run_expectations):
        try:
            return _one_run(name, run_mods, run_expectations)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError, Blocked) as error:
            # Recorded as a missing Worker result, so the run can only be incomplete.
            detail = error.detail if isinstance(error, Blocked) else f'{type(error).__name__}: {error}'
            return {'runDir': str(out_dir / name), 'order': [], 'prepareSeconds': 0.0,
                    'process': {'controllerError': detail}, 'worker': None, 'problem': 'controllerError', 'events': []}

    def _one_run(name, run_mods, run_expectations):
        run_dir = out_dir / name
        run_dir.mkdir()
        run_id = f'{result["runId"]}-{name}'
        nonce = secrets.token_hex(16)
        mark = time.monotonic()
        order = build_run_dir(run_dir, snapshot, request, run_mods, worker_dir, runtime,
                              expectations=run_expectations, run_id=run_id, nonce=nonce, deadline=deadline)
        prepared = time.monotonic() - mark
        wall = time.time()
        process = supervise(run_dir, limits, worker_environment(run_dir, limits, runtime))
        worker, problem, events = read_worker_output(run_dir, run_id, nonce, wall, limits['diagnostics'] + 10)
        if not keep_run_dirs:
            shutil.rmtree(run_dir / 'host', ignore_errors=True)
        return {'runDir': str(run_dir), 'order': order, 'prepareSeconds': round(prepared, 3), 'process': process,
                'worker': worker, 'problem': problem, 'events': events}

    baseline_mods = [m for m in mods if not m['target']]
    baseline_key = hashlib.sha256(json.dumps({
        'fingerprint': snapshot['fingerprint'], 'worker': result['tool']['workerSha256'], 'runtime': runtime,
        'official': request['official'], 'language': request['language'], 'limits': limits,
        'mods': [(m['packageId'], m['sha256']) for m in baseline_mods],
    }, sort_keys=True).encode()).hexdigest()
    baseline_run = None
    cache_file = Path(baseline_cache) / f'{baseline_key}.json' if baseline_cache else None
    if cache_file and cache_file.is_file():
        baseline_run = json.loads(cache_file.read_text(encoding='utf-8'))
        baseline_run['cached'] = True
    mark = time.monotonic()
    if baseline_run is None:
        baseline_run = one_run('baseline', baseline_mods, {k: [] for k in expectations})
        baseline_run['cached'] = False
        if cache_file and baseline_run['worker'] and baseline_run['worker'].get('executionStatus') == 'completed' \
                and not baseline_run['process'].get('killedFor'):
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            _write_json(cache_file, baseline_run)
    timings['baselineSeconds'] = round(time.monotonic() - mark, 3)
    mark = time.monotonic()
    target_run = one_run('target', mods, expectations)
    timings['targetSeconds'] = round(time.monotonic() - mark, 3)

    baseline_worker = baseline_run['worker']
    baseline_problem = baseline_run['problem'] or (
        None if baseline_worker and baseline_worker.get('executionStatus') == 'completed'
        else f'baseline run did not complete: {(baseline_worker or {}).get("failure") or baseline_run["process"].get("killedFor")}')
    status, execution, reasons, stages, fresh = evaluate(
        request, mods, target_run['worker'], target_run['problem'], target_run['events'],
        baseline_worker, baseline_problem, baseline_run['events'], target_run['process'], fidelity)
    worker = target_run['worker'] or {}
    result.update({
        'status': status, 'executionStatus': execution, 'reasons': reasons, 'stages': stages,
        'runtime': {'requested': runtime, **(worker.get('runtime') or {})},
        'modOrder': worker.get('modOrder'), 'runningMods': worker.get('runningMods'), 'modClasses': worker.get('modClasses'),
        'activeLanguage': worker.get('activeLanguage'),
        'checks': worker.get('checks'),
        'diagnostics': {
            'newInTarget': fresh,
            'target': worker.get('diagnosticsSummary'),
            'baseline': (baseline_worker or {}).get('diagnosticsSummary'),
            'baselineCached': baseline_run.get('cached', False),
            'eventsFile': str(Path(target_run['runDir']) / 'events.jsonl'),
        },
        'workerStages': worker.get('stages'), 'loadedAssemblies': worker.get('assemblies'),
        'skippedOfficialSteps': worker.get('skippedOfficialSteps'), 'deviations': worker.get('deviations'),
        'process': {'baseline': baseline_run['process'], 'target': target_run['process']},
        'scope': _scope(request, stages),
    })
    timings['baselinePrepareSeconds'] = baseline_run['prepareSeconds']
    timings['targetPrepareSeconds'] = target_run['prepareSeconds']
    return _finish(result, out_dir, started, timings)


def _scope(request, stages):
    checked = ['real mod/patch/def/translation loading of the selected language, including the official def error checks (DevMode)']
    if 'B' in request['levels']:
        checked.append('mod assembly loading and Mod constructors, startup static constructors, Harmony registry vs expected patches')
    not_checked = [
        'other languages than ' + request['language'],
        'anything that needs a map, a game, ticks, UI, rendering, audio output or Steam',
        'what Harmony patches do at run time (level C is not implemented)',
        'behaviour on other platforms or runtimes than the one recorded in "runtime"',
    ]
    if 'B' not in request['levels']:
        not_checked.insert(0, 'Harmony patch expectations (level B not requested; mod code still ran while loading)')
    return {'checked': checked, 'notChecked': not_checked}


def _finish(result, out_dir, started, timings):
    timings['totalSeconds'] = round(time.monotonic() - started, 3)
    result['timings'] = timings
    result['finishedAt'] = _now()
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / 'result.json', result)
    return result


def _now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _write_json(path, value):
    temp = Path(str(path) + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def _summary(result):
    lines = [f'status={result["status"]} executionStatus={result["executionStatus"]} fidelity={result.get("fidelity")}']
    for reason in result.get('reasons', []):
        lines.append(f'  - {reason["code"]}: {reason["detail"]}')
    for level, stage in (result.get('stages') or {}).items():
        if stage['status'] != 'notRequested':
            lines.append(f'  stage {level}: {stage["status"]}')
    lines.append(f'  total {result["timings"]["totalSeconds"]} s')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Test-only RimWorld MOD validation host (never starts the game).')
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare-game', help='copy the game folder into a private, read-only snapshot')
    prepare.add_argument('--source', required=True, help='the user-supplied RimWorld folder (Linux build)')
    prepare.add_argument('--snapshot', required=True, help='new directory for the snapshot')
    run = commands.add_parser('run', help='validate mods against a snapshot')
    run.add_argument('--snapshot', required=True)
    run.add_argument('--request', required=True, help='modValidationRequest JSON')
    run.add_argument('--out', required=True, help='new or empty directory for result.json and run evidence')
    run.add_argument('--worker', default=str(Path(__file__).resolve().parents[1] / 'worker' / 'bin'),
                     help='directory with the built Worker (default: worker/bin)')
    run.add_argument('--runtime', choices=('waylith', 'standard'), default='waylith',
                     help='waylith: the runtime shipped with the game (default); standard: stock .NET 10 (experimental)')
    run.add_argument('--baseline-cache', help='directory to reuse identical baseline runs')
    run.add_argument('--allow-unknown-build', action='store_true', help='run a build without an adapter (experimental)')
    run.add_argument('--verify-full', action='store_true', help='re-hash every snapshot file before running')
    run.add_argument('--keep-run-dirs', action='store_true', help='keep the per-run host directories for debugging')
    args = parser.parse_args(argv)
    if args.command == 'prepare-game':
        try:
            prepare_game(args.source, args.snapshot)
        except Blocked as blocked:
            print(f'blocked: {blocked.code}: {blocked.detail}', file=sys.stderr)
            return EXIT_CODES['blocked']
        return 0
    result = run_validation(args.snapshot, args.request, args.out, args.worker, runtime=args.runtime,
                            baseline_cache=args.baseline_cache, allow_unknown_build=args.allow_unknown_build,
                            verify_full=args.verify_full, keep_run_dirs=args.keep_run_dirs)
    print(_summary(result))
    print(f'result: {Path(args.out).resolve() / "result.json"}')
    return EXIT_CODES[result['status']]


if __name__ == '__main__':
    sys.exit(main())
