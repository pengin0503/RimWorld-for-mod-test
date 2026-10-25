"""Shared, read-only preflight for desktop users and AI automation."""
from __future__ import annotations

import hashlib
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import xml.parsers.expat as expat

try:
    from .audit_inputs import Audit, MIB, unsafe_path, xml_parser
except ImportError:
    from audit_inputs import Audit, MIB, unsafe_path, xml_parser


def load_profile(path):
    path = Path(path).resolve()
    if path.stat().st_size > MIB:
        raise ValueError('profile exceeds 1 MiB')
    profile = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(profile, dict):
        raise ValueError('profile must be a JSON object')
    for key in ('gameDir', 'saveDataDir'):
        value = profile.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f'{key} must be a nonempty path')
        profile[key] = str((path.parent / value).resolve())
    roots = profile.get('modRoots', [])
    if not isinstance(roots, list) or not all(isinstance(p, str) and p for p in roots):
        raise ValueError('modRoots must be an array of paths')
    profile['modRoots'] = [str((path.parent / p).resolve()) for p in roots]
    return profile


def _xml(data):
    parser = xml_parser()
    parser.Parse(data, True)
    return ET.fromstring(data)


def _linked(path):
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def _items(metadata, tag, version):
    versioned = metadata.find(f'{tag}ByVersion/v{version}')
    section = versioned if versioned is not None else metadata.find(tag)
    return list(section) if section is not None else []


def _folders(root, version, active, read):
    config = root / 'LoadFolders.xml'
    if config.exists():
        doc = _xml(read(config))
        if doc.tag != 'loadFolders':
            raise ValueError('unsupported LoadFolders root')
        section = doc.find('v' + version)
        if section is None:
            if any(re.fullmatch(r'v\d+(?:\.\d+)+', child.tag) for child in doc):
                raise ValueError('LoadFolders version fallback requires game verification')
            section = doc.find('default')
        if section is None:
            raise ValueError('LoadFolders version fallback requires game verification')
        selected = []
        for item in section:
            if item.tag != 'li' or set(item.attrib) - {'IfModActive', 'IfModNotActive'}:
                raise ValueError('unsupported LoadFolders condition')
            enabled = True
            for key, identifier in item.attrib.items():
                if any(c in identifier for c in ',;|'):
                    raise ValueError('compound LoadFolders conditions require game verification')
                present = identifier.strip().lower() in active
                enabled &= present if key == 'IfModActive' else not present
            if not enabled:
                continue
            name = (item.text or '').strip()
            if name in ('/', '.'):
                folder = root
            elif unsafe_path(name):
                raise ValueError('unsafe LoadFolders path')
            else:
                folder = root / name
            if not folder.is_dir() or _linked(folder) or not folder.resolve().is_relative_to(root.resolve()):
                raise ValueError('missing or linked LoadFolders directory')
            selected.append(folder)
        return list(dict.fromkeys(selected))
    version_dirs = [p for p in root.iterdir() if p.is_dir() and re.fullmatch(r'\d+\.\d+', p.name)]
    if version_dirs and not (root / version).is_dir():
        raise ValueError('version folder fallback requires game verification')
    choices = (root, root / 'Common', root / version)
    if any(_linked(p) for p in choices):
        raise ValueError('linked default content directories are not inspected')
    return [p for p in choices if p.is_dir()]


def check_profile(profile):
    start = time.monotonic()
    audit = Audit()
    report = audit.report
    report.update(recordType='modPreflight', activeMods=[], profile=profile,
                  coverage={'metadata': True, 'xmlSyntax': 'selected Defs/Patches only',
                            'translations': 'notRun', 'patchApplication': 'notRun',
                            'harmony': 'notRun', 'gameplay': 'notRun'},
                  statistics={'xmlFilesChecked': 0, 'dllFilesHashed': 0},
                  warnings=[])
    fingerprints = {}
    observed = {}
    total = 0
    read_anchors = set()

    def read(path):
        nonlocal total
        path = Path(path)
        if _linked(path) or not path.is_file():
            raise ValueError('missing file or symlink: ' + str(path))
        for parent in path.parents:
            if parent in read_anchors:
                break
            if _linked(parent):
                raise ValueError('linked parent directory is not inspected: ' + str(parent))
        before = path.stat()
        if before.st_size > 64 * MIB or total + before.st_size > 512 * MIB:
            raise ValueError('preflight input byte limit exceeded')
        with path.open('rb') as stream:
            data = stream.read(64 * MIB + 1)
        after = path.stat()
        identity = (after.st_size, after.st_mtime_ns)
        if len(data) > 64 * MIB or (before.st_size, before.st_mtime_ns) != identity:
            raise ValueError('input changed while reading or exceeds limit')
        total += len(data)
        key = str(path.resolve())
        digest = hashlib.sha256(data).hexdigest()
        if key in fingerprints and fingerprints[key] != digest:
            raise ValueError('input changed between reads')
        fingerprints[key] = digest
        observed[path] = identity
        return data

    try:
        if not isinstance(profile, dict) or profile.get('schemaVersion') != 1:
            raise ValueError('unsupported profile schema')
        version = profile.get('gameVersion', '1.7')
        if not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+', version):
            raise ValueError('gameVersion must be major.minor')
        game, save = Path(profile['gameDir']), Path(profile['saveDataDir'])
        roots = profile.get('modRoots', [])
        if not isinstance(roots, list) or not all(isinstance(p, str) and p for p in roots):
            raise ValueError('invalid modRoots')
        if not game.is_absolute() or not save.is_absolute() or not game.is_dir() or not save.is_dir():
            raise ValueError('gameDir and saveDataDir must be existing absolute directories')
        read_anchors.update({game, game.resolve(), save, save.resolve(), *(Path(p).resolve() for p in roots)})
        executables = [p for p in (game / 'RimWorld.exe', game / 'RimWorld') if p.is_file()]
        if not executables:
            raise ValueError('official executable name not found in gameDir')
        for path in executables:
            read(path)
        for name in ('RimWorld.dll', 'Assembly-CSharp.dll', 'Waylith.dll', 'UnityStubs.dll',
                     'RimWorld.runtimeconfig.json', 'RimWorld.deps.json'):
            path = game / name
            if path.exists():
                read(path)
        config = _xml(read(save / 'Config/ModsConfig.xml'))
        if config.tag != 'ModsConfigData':
            raise ValueError('unsupported ModsConfig root')
        config_version = config.findtext('version', '')
        if config_version and not (config_version == version or config_version.startswith(version + '.')):
            audit.add('versionMismatch', 'ModsConfig version differs from profile')
        active = [(p.text or '').strip().lower() for p in config.findall('./activeMods/li')]
        if not active or any(not p for p in active) or len(set(active)) != len(active):
            audit.add('activeMods', 'active MOD list is empty, blank or duplicated')
        if not active or active[0] != 'ludeon.rimworld':
            audit.add('coreOrder', 'Core must be the first active MOD')
        candidates = {}
        search_roots = [game / 'Data', game / 'Mods', *map(Path, roots)]
        for automatic in (game / 'Data', game / 'Mods'):
            if _linked(automatic):
                audit.add('modRoot', 'automatic Data/Mods search root is linked', automatic, incomplete=True)
        search_roots = [p for p in search_roots if not _linked(p) or p in list(map(Path, roots))]
        indexed = set()
        for search in dict.fromkeys(p.resolve() for p in search_roots):
            if not search.is_dir():
                if search in [Path(p).resolve() for p in roots]:
                    audit.add('modRoot', 'configured mod root does not exist', search)
                continue
            children = sorted(search.iterdir())
            if len(children) > 10_000:
                raise ValueError('mod directory count limit exceeded')
            for folder in children:
                if not folder.is_dir() or _linked(folder) or folder.resolve() in indexed:
                    continue
                about = folder / 'About/About.xml'
                if not about.is_file():
                    continue
                indexed.add(folder.resolve())
                try:
                    metadata = _xml(read(about))
                    identifier = metadata.findtext('packageId', '').strip().lower()
                    if metadata.tag != 'ModMetaData' or not identifier:
                        raise ValueError('invalid About metadata')
                    candidates.setdefault(identifier, []).append((folder, metadata))
                except (OSError, ValueError, LookupError, expat.ExpatError, ET.ParseError) as error:
                    audit.add('aboutMetadata', error, about, incomplete=True)
        resolved = []
        for identifier in active:
            key = identifier
            if key not in candidates and key.endswith('_steam'):
                key = key[:-6]
            choices = candidates.get(key, [])
            if len(choices) != 1:
                audit.add('ambiguousPackage' if choices else 'missingPackage',
                          'active package source is ambiguous' if choices else 'active package not found', identifier)
                continue
            if key in resolved:
                audit.add('activeMods', 'multiple active identifiers resolve to one package', key)
            resolved.append(key)
        report['activeMods'] = resolved
        positions = {p: i for i, p in enumerate(resolved)}
        for identifier in resolved:
            folder, metadata = candidates[identifier][0]
            for field in list(metadata):
                if field.tag.endswith('ByVersion') and len(field) and field.find('v' + version) is None:
                    audit.add('metadataVersionFallback', 'versioned metadata fallback is not verified', identifier, incomplete=True)
            supported = [(p.text or '').strip() for p in metadata.findall('./supportedVersions/li')]
            if identifier != 'ludeon.rimworld' and supported and version not in supported:
                audit.add('versionMismatch', 'MOD supportedVersions excludes selected game version', identifier)
            for item in _items(metadata, 'modDependencies', version):
                dependency = item.findtext('packageId', '').strip().lower()
                if not dependency or dependency not in positions:
                    audit.add('dependencyMissing', 'required package is not active', dependency or identifier)
            for item in _items(metadata, 'incompatibleWith', version):
                conflict = (item.text or '').strip().lower()
                if conflict in positions:
                    audit.add('incompatible', f'{identifier} conflicts with {conflict}')
            for tag, before in [('forceLoadBefore', True), ('forceLoadAfter', False)]:
                for item in _items(metadata, tag, version):
                    other = (item.text or '').strip().lower()
                    if other in positions and ((positions[identifier] > positions[other]) == before):
                        audit.add('loadOrder', f'{identifier}: {tag} {other}')
            for tag in ('loadBefore', 'loadAfter'):
                if _items(metadata, tag, version):
                    if len(report['warnings']) < 200:
                        report['warnings'].append(f'{identifier}: advisory {tag} is not enforced')
            try:
                folders = _folders(folder, version, set(resolved), read)
            except (OSError, ValueError, LookupError, expat.ExpatError, ET.ParseError) as error:
                audit.add('loadFolders', error, folder, incomplete=True)
                continue
            for content in folders:
                for category in ('Defs', 'Patches', 'Assemblies'):
                    base = content / category
                    if not base.exists():
                        continue
                    def traversal_error(error):
                        audit.add('directoryRead', error, getattr(error, 'filename', None) or base, incomplete=True)
                    for parent, directories, files in os.walk(base, followlinks=False, onerror=traversal_error):
                        linked = [d for d in directories if _linked(Path(parent) / d)]
                        if linked or _linked(Path(parent)):
                            audit.add('symlink', 'linked content directories are not inspected', parent, incomplete=True)
                            directories[:] = [d for d in directories if d not in linked]
                            if _linked(Path(parent)):
                                continue
                        for name in sorted(files):
                            path = Path(parent) / name
                            suffix = path.suffix.lower()
                            if suffix not in ('.xml', '.dll'):
                                continue
                            if len(fingerprints) >= 100_000:
                                raise ValueError('file count limit exceeded')
                            try:
                                data = read(path)
                                if suffix == '.xml':
                                    _xml(data)
                                    report['statistics']['xmlFilesChecked'] += 1
                                else:
                                    report['statistics']['dllFilesHashed'] += 1
                            except (OSError, ValueError, LookupError, expat.ExpatError, ET.ParseError) as error:
                                audit.add('xmlSyntax' if suffix == '.xml' else 'fileRead', error, path)
        for path, identity in observed.items():
            current = path.stat()
            if (current.st_size, current.st_mtime_ns) != identity:
                audit.add('inputChanged', 'input changed during preflight', path, incomplete=True)
    except (OSError, ValueError, KeyError, TypeError, LookupError, expat.ExpatError, ET.ParseError) as error:
        audit.add('profileInput', error)
    fingerprint_input = {'profile': profile, 'files': fingerprints}
    report['fingerprint'] = hashlib.sha256(json.dumps(fingerprint_input, sort_keys=True).encode()).hexdigest()
    report['statistics']['filesFingerprinted'] = len(fingerprints)
    report['elapsedSeconds'] = round(time.monotonic() - start, 4)
    return report


def launch_command(profile, report, platform):
    if report.get('recordType') != 'modPreflight' or report.get('auditStatus') != 'passed':
        raise ValueError('a passed preflight report is required')
    fresh = check_profile(profile)
    if fresh['auditStatus'] != 'passed' or report.get('fingerprint') != fresh['fingerprint']:
        raise ValueError('configuration changed; run preflight again')
    names = {'windows': 'RimWorld.exe', 'linux': 'RimWorld'}
    if platform not in names:
        raise ValueError('unsupported game platform')
    executable = Path(profile['gameDir']) / names[platform]
    if not executable.is_file() or _linked(executable):
        raise ValueError('official executable is missing or linked')
    save = str(Path(profile['saveDataDir']))
    if '=' in save or save.endswith(('"', "'")):
        raise ValueError('selected save-data path cannot be represented by this game argument parser')
    return [str(executable), '-savedatafolder=' + save]


def write_json(path, data, profile, profile_path=None):
    destination = Path(os.path.abspath(path))
    resolved_destination = destination.resolve()
    protected = [profile['gameDir'], profile['saveDataDir'], *profile.get('modRoots', [])]
    if any(destination.is_relative_to(Path(os.path.abspath(p)))
           or resolved_destination.is_relative_to(Path(p).resolve()) for p in protected):
        raise ValueError('output must be outside game, save-data and MOD directories')
    if profile_path is not None:
        source = Path(profile_path).resolve()
        if destination == source or (destination.exists() and os.path.samefile(destination, source)):
            raise ValueError('report must not overwrite profile')
    temporary = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destination.parent,
                                         prefix='.preflight-', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check', help='read active MOD configuration without starting the game')
    check.add_argument('--profile', type=Path, required=True)
    check.add_argument('--output', type=Path)
    play = commands.add_parser('play', help='explicitly request normal game launch after rechecking')
    play.add_argument('--profile', type=Path, required=True)
    play.add_argument('--report', type=Path, required=True)
    play.add_argument('--dry-run', action='store_true')
    play.add_argument('--acknowledge-static-only', action='store_true')
    desktop = commands.add_parser('desktop', help='open local desktop interface')
    desktop.add_argument('--profile', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'desktop':
            try:
                from .preflight_gui import run_gui
            except ImportError:
                from preflight_gui import run_gui
            run_gui(args.profile)
            return 0
        profile = load_profile(args.profile)
        if args.command == 'check':
            report = check_profile(profile)
            if args.output:
                write_json(args.output, report, profile, args.profile)
            else:
                print(json.dumps(report, ensure_ascii=True, indent=2))
            return {'passed': 0, 'failed': 1, 'incomplete': 2}[report['auditStatus']]
        if not args.dry_run and not args.acknowledge_static_only:
            raise ValueError('use --acknowledge-static-only to request normal game launch')
        if args.report.stat().st_size > 16 * MIB:
            raise ValueError('report exceeds size limit')
        report = json.loads(args.report.read_text(encoding='utf-8-sig'))
        if not isinstance(report, dict):
            raise ValueError('invalid preflight report')
        platform = 'windows' if sys.platform == 'win32' else 'linux' if sys.platform.startswith('linux') else ''
        command = launch_command(profile, report, platform)
        result = {'launchRequested': False, 'gameVerification': 'notRun', 'launchCommand': command}
        if not args.dry_run:
            child = subprocess.Popen(command, cwd=profile['gameDir'], stdin=subprocess.DEVNULL)
            result.update(launchRequested=True, pid=child.pid)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        print(json.dumps({'recordType': 'modPreflight', 'schemaVersion': 1, 'auditStatus': 'failed',
                          'gameVerification': 'notRun', 'error': str(error)}, ensure_ascii=True, indent=2))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
