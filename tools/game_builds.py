"""Game build identity and per-build qualification records.

The host follows RimWorld 1.7 updates without code changes:

* The build is read from the game's own ``Version.txt`` (``1.7.<build> rev<revision>``).
  Every build of a supported major.minor family (only 1.7 today) gets an adapter
  automatically; the Worker binds every game member it uses by reflection before
  the engine starts, so a build that really changed one of them stops with
  ``workerAdapterMismatch`` naming the member instead of failing somewhere later.
* Whether results on a build are ``qualified`` is decided by a qualification record
  for exactly that build: the identity hashes of its managed game files, the
  runtime it was compared on, the levels and features that matched the official
  game, and where the evidence is. Without a matching record a build runs as
  ``experimental``.

Records come from two places:

* committed: ``validation-data/<build id>/qualification.json`` in this repository
  (reviewed in a pull request; may be written by hand or by the automatic
  qualification);
* private: a directory given by ``--qualification-store`` or the environment
  variable ``RWMT_QUALIFICATION_STORE``, written by
  ``experiments/official-comparison/qualify_build.py`` after it compared the build
  with the official game. A private record only applies to the exact Worker build
  that was compared (``worker.sha256``), because it has not been reviewed.

No record is ever inferred from a version number, and a record whose hashes do not
match the snapshot is ignored.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

RECORD_TYPE = 'rwmtBuildQualification'
SCHEMA_VERSION = 1
STORE_ENV = 'RWMT_QUALIFICATION_STORE'
DATA_ROOT = Path(__file__).resolve().parent.parent / 'validation-data'
RECORD_NAME = 'qualification.json'
MAX_RECORD_BYTES = 256 * 1024

VERSION = re.compile(r'(\d{1,4})\.(\d{1,4})\.(\d{1,7}) rev(\d{1,9})')
# Managed game files whose hashes identify a build in a record. Native runtime files
# are recorded per platform (``runtimeSha256``) because they differ between platforms.
IDENTITY_FILES = ('Assembly-CSharp.dll', 'RimWorld.dll', 'Waylith.dll', 'UnityStubs.dll', 'Waylith.UnityCompat.dll')
RUNTIME_FILES = {'linux-x64': ('libcoreclr.so', 'System.Private.CoreLib.dll'),
                 'windows-x64': ('coreclr.dll', 'System.Private.CoreLib.dll')}
LEVELS = ('A', 'B', 'C', 'D')
FEATURES = ('map',)
EXPERIMENTAL_FEATURES = ('bounded-tick.v1', 'bounded-tick.v2')
METHODS = ('manual', 'automatic')
SHA256 = re.compile(r'[0-9a-f]{64}')
BUILD_ID = re.compile(r'\d{1,4}\.\d{1,4}\.\d{1,7}-rev\d{1,9}')

# Major.minor versions the Worker is written for. A new major.minor (1.8, 2.0) is a
# different game release with its own loader and API, so it is never followed
# automatically: it stops with ``unknownBuild`` until someone adds the family here.
FAMILIES = {
    (1, 7): {'id': 'rimworld-1.7'},
}


class RecordError(ValueError):
    """A qualification record is malformed; it is never used."""


def parse_version(text):
    """``(major, minor, build, revision)`` from a Version.txt line, or None."""
    if not isinstance(text, str):
        return None
    match = VERSION.fullmatch(text.strip())
    return tuple(int(part) for part in match.groups()) if match else None


def build_id(text):
    """The folder and adapter suffix for a version, e.g. ``1.7.5014-rev1195``."""
    parsed = parse_version(text)
    if parsed is None:
        raise ValueError(f'not a RimWorld build version: {text!r}')
    return f'{parsed[0]}.{parsed[1]}.{parsed[2]}-rev{parsed[3]}'


def family(text):
    """The supported family of a version (a FAMILIES entry plus its key), or None."""
    parsed = parse_version(text)
    if parsed is None or parsed[:2] not in FAMILIES:
        return None
    return {**FAMILIES[parsed[:2]], 'majorMinor': f'{parsed[0]}.{parsed[1]}'}


def game_version_numbers(text):
    """(major, minor, build) for load-folder and dependency rules, or None."""
    parsed = parse_version(text)
    return parsed[:3] if parsed else None


def _hashes(value, names=None):
    if not isinstance(value, dict) or not value:
        raise RecordError('hash table missing')
    if names is not None and set(value) != set(names):
        raise RecordError('hash table lists other files than expected')
    for name, digest in value.items():
        if not isinstance(name, str) or not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise RecordError('invalid hash entry')
    return dict(value)


def _names(value, allowed, what):
    if not isinstance(value, list) or len(set(value)) != len(value) or any(v not in allowed for v in value):
        raise RecordError(f'invalid {what}')
    return tuple(value)


def _text(value, what, limit=300):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise RecordError(f'invalid {what}')
    return value


def validate_record(record):
    """Return a normalized copy of a record or raise RecordError. Unknown fields are rejected."""
    allowed = {'recordType', 'schemaVersion', 'gameVersion', 'buildId', 'method', 'createdAt', 'identitySha256',
               'experimentalFeatures', 'qualified', 'worker', 'comparison', 'note'}
    if not isinstance(record, dict) or set(record) - allowed:
        raise RecordError('unsupported record fields')
    if record.get('recordType') != RECORD_TYPE or record.get('schemaVersion') != SCHEMA_VERSION:
        raise RecordError('not a build qualification record')
    version = record.get('gameVersion')
    if parse_version(version) is None or record.get('buildId') != build_id(version):
        raise RecordError('gameVersion and buildId do not agree')
    if record.get('method') not in METHODS:
        raise RecordError('invalid method')
    normalized = {
        'recordType': RECORD_TYPE, 'schemaVersion': SCHEMA_VERSION, 'gameVersion': version, 'buildId': record['buildId'],
        'method': record['method'], 'identitySha256': _hashes(record.get('identitySha256'), IDENTITY_FILES),
        'experimentalFeatures': _names(record.get('experimentalFeatures', []), EXPERIMENTAL_FEATURES, 'experimental features'),
        'qualified': [],
    }
    for key in ('createdAt', 'note'):
        if key in record:
            normalized[key] = _text(record[key], key, 2000)
    if 'comparison' in record:
        if not isinstance(record['comparison'], dict):
            raise RecordError('invalid comparison summary')
        normalized['comparison'] = record['comparison']
    if 'worker' in record:
        worker = record['worker']
        if not isinstance(worker, dict) or set(worker) != {'sha256'} or not SHA256.fullmatch(str(worker['sha256'])):
            raise RecordError('invalid worker identity')
        normalized['worker'] = {'sha256': worker['sha256']}
    rows = record.get('qualified')
    if not isinstance(rows, list):
        raise RecordError('qualified must be a list')
    seen = set()
    for row in rows:
        keys = {'platform', 'runtime', 'levels', 'features', 'runtimeSha256', 'evidence', 'featureEvidence'}
        if not isinstance(row, dict) or set(row) - keys or not {'platform', 'runtime', 'levels', 'runtimeSha256', 'evidence'} <= set(row):
            raise RecordError('invalid qualified entry')
        platform, runtime = row['platform'], row['runtime']
        if platform not in RUNTIME_FILES or runtime not in ('waylith', 'standard') or (platform, runtime) in seen:
            raise RecordError('invalid or repeated platform/runtime')
        seen.add((platform, runtime))
        levels = _names(row['levels'], LEVELS, 'levels')
        if not levels:
            raise RecordError('a qualified entry needs at least one level')
        features = _names(row.get('features', []), FEATURES, 'features')
        evidence = row.get('featureEvidence', {})
        if not isinstance(evidence, dict) or set(evidence) - set(features):
            raise RecordError('feature evidence for a feature that is not qualified')
        normalized['qualified'].append({
            'platform': platform, 'runtime': runtime, 'levels': levels, 'features': features,
            'runtimeSha256': _hashes(row['runtimeSha256'], RUNTIME_FILES[platform]),
            'evidence': _text(row['evidence'], 'evidence'),
            'featureEvidence': {k: _text(v, 'feature evidence') for k, v in evidence.items()},
        })
    return normalized


def read_record(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_RECORD_BYTES:
        raise RecordError('record file missing, linked or too large')
    try:
        return validate_record(json.loads(path.read_text(encoding='utf-8')))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise RecordError('record is not valid JSON') from error


def adapter_from_record(record, *, source):
    """The adapter shape the Controller uses (see validation_host.run_validation)."""
    qualified = {}
    for row in record['qualified']:
        qualified[(row['platform'], row['runtime'])] = {
            'levels': row['levels'], 'runtimeSha256': row['runtimeSha256'], 'evidence': row['evidence'],
            'features': row['features'], 'featureEvidence': row['featureEvidence'],
        }
    adapter = {'version': record['gameVersion'], 'buildId': record['buildId'], 'sha256': record['identitySha256'],
               'experimentalFeatures': record['experimentalFeatures'], 'qualified': qualified,
               'record': {'source': source, 'method': record['method']}}
    if 'worker' in record:
        adapter['worker'] = record['worker']
    return adapter


def committed_adapters(root=DATA_ROOT):
    """Adapters from the reviewed records in validation-data/, keyed ``rimworld-<build id>``.

    A malformed committed record is a programming error and raises, so tests catch it."""
    adapters = {}
    root = Path(root)
    if not root.is_dir():
        return adapters
    for folder in sorted(root.iterdir()):
        path = folder / RECORD_NAME
        if not path.is_file():
            continue
        record = read_record(path)
        if record['buildId'] != folder.name:
            raise RecordError(f'{path}: buildId {record["buildId"]} does not match its folder')
        if 'worker' in record:
            raise RecordError(f'{path}: committed records apply to every Worker build; drop worker.sha256')
        adapters[f'rimworld-{record["buildId"]}'] = adapter_from_record(record, source='committed')
    return adapters


def store_directory(store=None):
    """The private qualification store: the argument, else $RWMT_QUALIFICATION_STORE, else None."""
    value = store if store is not None else os.environ.get(STORE_ENV)
    return Path(value).expanduser() if value else None


def private_records(store):
    """Valid records in a private store; malformed files are reported, never used."""
    directory = store_directory(store)
    records, problems = [], []
    if directory is None or not directory.is_dir() or directory.is_symlink():
        return records, problems
    for path in sorted(directory.glob('*.json')):
        try:
            records.append((path, read_record(path)))
        except RecordError as error:
            problems.append(f'{path.name}: {error}')
    return records, problems


def identity_matches(manifest, record_or_adapter):
    hashes = record_or_adapter.get('identitySha256') or record_or_adapter.get('sha256') or {}
    return bool(hashes) and all(manifest.get(rel, {}).get('sha256') == value for rel, value in hashes.items())


def record_file_name(record, fingerprint):
    return f'{record["buildId"]}-{fingerprint[:16]}.json'
