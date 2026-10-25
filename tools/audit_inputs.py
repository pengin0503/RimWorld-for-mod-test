"""Read-only source checks. A passed audit never means a passed game test."""
from __future__ import annotations

import hashlib
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import tempfile
import unicodedata
import xml.parsers.expat as expat
import zipfile
import zlib

MIB = 1024 * 1024
MAX_METADATA_BYTES = 16 * MIB
MAX_DIAGNOSTICS = 200


class Audit:
    def __init__(self):
        self.report = {
            'recordType': 'offlineInputAudit', 'schemaVersion': 1,
            'auditStatus': 'passed', 'gameVerification': 'notRun',
            'diagnostics': [], 'omittedDiagnostics': 0,
        }

    def add(self, code, message, path=None, *, incomplete=False):
        status = 'incomplete' if incomplete else 'failed'
        if self.report['auditStatus'] != 'failed':
            self.report['auditStatus'] = status
        item = {'code': code, 'message': str(message)}
        if path is not None:
            item['path'] = str(path)
        if len(self.report['diagnostics']) < MAX_DIAGNOSTICS:
            self.report['diagnostics'].append(item)
        else:
            self.report['omittedDiagnostics'] += 1


def unsafe_path(path):
    return (not path or '\\' in path or path.startswith('/')
            or re.match(r'^[A-Za-z]:', path) is not None
            or any(p in ('', '.', '..') for p in path.rstrip('/').split('/'))
            or any(ord(c) < 32 for c in path))


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def metadata_text(path):
    with Path(path).open('rb') as stream:
        data = stream.read(MAX_METADATA_BYTES + 1)
    if len(data) > MAX_METADATA_BYTES:
        raise ValueError('metadata exceeds 16 MiB')
    return data.decode('utf-8-sig')


def read_manifest(path):
    result = {}
    for number, line in enumerate(metadata_text(path).splitlines(), 1):
        if not line:
            continue
        parts = line.rsplit(' ', 1)
        if (len(parts) != 2 or unsafe_path(parts[0])
                or not re.fullmatch(r'[0-9A-Fa-f]{64}', parts[1])):
            raise ValueError(f'invalid manifest line {number}')
        name, digest = parts
        if name in result:
            raise ValueError(f'duplicate manifest path at line {number}')
        result[name] = digest.lower()
        if len(result) > 100_000:
            raise ValueError('manifest exceeds 100000 paths')
    if not result:
        raise ValueError('empty manifest')
    return result


def xml_parser():
    parser = expat.ParserCreate()

    def reject_doctype(*_):
        raise ValueError('DOCTYPE is not supported by this static audit')

    parser.StartDoctypeDeclHandler = reject_doctype
    return parser


def entry_chunks(archive, info, boundary):
    """Decode independently of ZipExtFile's declared-size truncation."""
    source = archive.fp
    source.seek(info.header_offset)
    header = source.read(30)
    if len(header) != 30:
        raise zipfile.BadZipFile('truncated local header')
    signature, _, flags, method, _, _, _, _, _, name_size, extra_size = struct.unpack('<4s5H3I2H', header)
    if signature != b'PK\x03\x04' or flags != info.flag_bits or method != info.compress_type:
        raise zipfile.BadZipFile('local and central headers disagree')
    name = source.read(name_size).decode('utf-8' if flags & 0x800 else 'cp437')
    if name != info.orig_filename:
        raise zipfile.BadZipFile('local and central filenames disagree')
    source.seek(extra_size, 1)
    if source.tell() + info.compress_size > boundary:
        raise zipfile.BadZipFile('entry overlaps another header or central directory')
    if flags & 1 or method not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise NotImplementedError('only unencrypted Stored and Deflate entries are supported')
    decoder = zlib.decompressobj(-15) if method == zipfile.ZIP_DEFLATED else None
    remaining = info.compress_size
    actual = crc = 0
    while remaining:
        chunk = source.read(min(64 * 1024, remaining))
        if not chunk:
            raise zipfile.BadZipFile('truncated compressed entry')
        remaining -= len(chunk)
        pending = chunk
        more = True
        while more:
            data = decoder.decompress(pending, 64 * 1024) if decoder else pending
            pending = decoder.unconsumed_tail if decoder else b''
            actual += len(data)
            if actual > info.file_size:
                raise zipfile.BadZipFile('decoded bytes exceed declared uncompressed size')
            crc = zlib.crc32(data, crc)
            if decoder and decoder.unused_data:
                raise zipfile.BadZipFile('trailing compressed bytes')
            if data:
                yield data
            more = bool(pending) or bool(decoder and len(data) == 64 * 1024 and not decoder.eof)
    if decoder and not decoder.eof:
        raise zipfile.BadZipFile('deflate stream did not reach end of stream')
    if actual != info.file_size or crc != info.CRC:
        raise zipfile.BadZipFile('decoded size or CRC differs from central directory')


def audit_zip(path, manifest=None, scopes=(), *, max_entry_bytes=256 * MIB,
              max_total_bytes=512 * MIB, max_entries=100_000):
    audit = Audit()
    report = audit.report
    report['input'] = {'name': Path(path).name}
    report['limits'] = {'entryBytes': max_entry_bytes, 'totalBytes': max_total_bytes,
                        'entries': max_entries, 'diagnostics': MAX_DIAGNOSTICS}
    report['coverage'] = {'zipEntryCrc': 'partial', 'xmlSyntax': 'topLevelOnly',
                          'nestedArchives': 'notInspected', 'assetDecoding': 'notRun'}
    stats = report['statistics'] = {'entriesDeclared': 0, 'payloadFilesRead': 0,
                                    'bytesRead': 0, 'xmlFilesChecked': 0}
    if min(max_entry_bytes, max_total_bytes, max_entries) <= 0:
        audit.add('arguments', 'limits must be positive')
        return report
    if scopes and manifest is None:
        audit.add('arguments', 'scopes require a manifest')
        return report
    if any(unsafe_path(s) or not s.endswith('/') for s in scopes):
        audit.add('arguments', 'each scope must be a safe directory ending in /')
        return report
    expected = None
    if manifest is not None:
        try:
            expected = read_manifest(manifest)
            expected = {p: h for p, h in expected.items()
                        if not scopes or p.startswith(tuple(scopes))}
            if not expected:
                raise ValueError('scope selects no manifest paths')
        except (OSError, ValueError) as error:
            audit.add('manifest', error)
            return report
    hashes = {}
    seen = {}
    files_seen = set()
    parents_seen = set()
    all_read = True
    try:
        report['input']['sha256'] = sha256_file(path)
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            stats['entriesDeclared'] = len(entries)
            if len(entries) > max_entries:
                audit.add('limit', 'archive entry count exceeds limit', incomplete=True)
                return report
            offsets = sorted({e.header_offset for e in entries} | {archive.start_dir})
            boundaries = dict(zip(offsets, offsets[1:]))
            for info in entries:
                name = info.filename
                if unsafe_path(info.orig_filename):
                    audit.add('unsafePath', 'ambiguous or unsafe archive path', name)
                normalized = unicodedata.normalize('NFC', name.rstrip('/')).casefold()
                if normalized in seen and not (info.is_dir() and seen[normalized] == name):
                    audit.add('pathCollision', 'duplicate, case or Unicode collision', name)
                seen[normalized] = name
                parents = [str(p) for p in PurePosixPath(normalized).parents if str(p) != '.']
                if any(p in files_seen for p in parents) or (not info.is_dir() and normalized in parents_seen):
                    audit.add('pathCollision', 'regular file conflicts with a parent directory', name)
                parents_seen.update(parents)
                if not info.is_dir():
                    files_seen.add(normalized)
                if stat.S_ISLNK(info.external_attr >> 16):
                    audit.add('link', 'symlink is not a regular resource', name)
                metadata = name.startswith('__MACOSX/') or PurePosixPath(name).name == '.DS_Store'
                if not metadata and any(ord(c) > 127 for c in name) and not info.flag_bits & 0x800:
                    audit.add('filenameEncoding', 'non-ASCII name without UTF-8 ZIP flag', name, incomplete=True)
                if info.file_size > max_entry_bytes or stats['bytesRead'] + info.file_size > max_total_bytes:
                    audit.add('limit', 'uncompressed byte limit would be exceeded', name, incomplete=True)
                    all_read = False
                    break
                parser = xml_parser() if name.lower().endswith('.xml') and not metadata else None
                digest = hashlib.sha256()
                entry_bytes = 0
                try:
                    for chunk in entry_chunks(archive, info, boundaries.get(info.header_offset, archive.start_dir)):
                        entry_bytes += len(chunk)
                        stats['bytesRead'] += len(chunk)
                        if entry_bytes > max_entry_bytes or stats['bytesRead'] > max_total_bytes:
                            audit.add('limit', 'actual uncompressed bytes exceed limit', name, incomplete=True)
                            all_read = False
                            break
                        digest.update(chunk)
                        if parser is not None:
                            try:
                                parser.Parse(chunk, False)
                            except (expat.ExpatError, ValueError, LookupError) as error:
                                audit.add('xmlSyntax', error, name)
                                parser = None
                    if not all_read:
                        break
                    if parser is not None:
                        try:
                            parser.Parse(b'', True)
                            stats['xmlFilesChecked'] += 1
                        except (expat.ExpatError, ValueError, LookupError) as error:
                            audit.add('xmlSyntax', error, name)
                    if not info.is_dir() and not metadata:
                        hashes[name] = digest.hexdigest()
                        stats['payloadFilesRead'] += 1
                except (NotImplementedError, RuntimeError) as error:
                    audit.add('unsupportedCompression', error, name, incomplete=True)
                    all_read = False
                    break
                except (zipfile.BadZipFile, OSError, EOFError, ValueError, zlib.error) as error:
                    audit.add('archiveRead', error, name)
                    all_read = False
                    break
            if all_read:
                report['coverage']['zipEntryCrc'] = 'all'
    except (zipfile.BadZipFile, OSError, EOFError, ValueError) as error:
        audit.add('archiveRead', error)
        all_read = False
    if all_read and not hashes:
        audit.add('emptyArchive', 'no payload files were inspected')
    if expected is not None:
        matching = {p for p, h in hashes.items() if expected.get(p) == h}
        verified_hashes = {hashes[p] for p in matching}
        aliases = 0
        covered = 0
        for p, h in expected.items():
            if p in hashes and hashes[p] != h:
                audit.add('hashMismatch', 'file SHA-256 differs from manifest', p)
            if p in matching:
                covered += 1
            elif p not in hashes and h in verified_hashes:
                aliases += 1
                covered += 1
            else:
                audit.add('missingContent', 'requested content not verified', p, incomplete=not all_read)
        report['manifestComparison'] = {'requestedPaths': len(expected),
            'physicalPathsMatched': len(matching), 'contentCoveredPaths': covered,
            'aliasCoveredPaths': aliases, 'runtimeAliasResolution': 'notRun'}
    return report


def audit_metadata(manifest_path, textures_path):
    audit = Audit()
    report = audit.report
    report['coverage'] = {'manifestFormat': True, 'texturePathAgreement': True,
                          'resourcePayload': 'notInspected', 'assetDecoding': 'notRun'}
    try:
        manifest = read_manifest(manifest_path)
        textures = set()
        for number, line in enumerate(metadata_text(textures_path).splitlines(), 1):
            if not line:
                continue
            parts = line.rsplit(' ', 6)
            if len(parts) != 7 or unsafe_path(parts[0]):
                raise ValueError(f'invalid textures.info line {number}')
            for value in parts[1:]:
                int(value)
            if parts[0] in textures:
                raise ValueError(f'duplicate textures.info path at line {number}')
            textures.add(parts[0])
            if len(textures) > 100_000:
                raise ValueError('textures.info exceeds 100000 paths')
        expected = {p for p in manifest if p.startswith('Resources/Textures/')}
        if not expected or not textures:
            raise ValueError('no texture paths to compare')
        for path in sorted(expected - textures):
            audit.add('textureMetadataMissing', 'manifest texture absent from metadata', path)
        for path in sorted(textures - expected):
            audit.add('textureManifestMissing', 'metadata texture absent from manifest', path)
        report['statistics'] = {'manifestPaths': len(manifest), 'textureEntries': len(textures),
            'manifestTexturePaths': len(expected), 'distinctContentHashes': len(set(manifest.values()))}
        report['inputs'] = [{'name': Path(p).name, 'sha256': sha256_file(p)}
                            for p in (manifest_path, textures_path)]
    except (OSError, ValueError) as error:
        audit.add('metadata', error)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    zip_parser = sub.add_parser('zip', help='inspect outer ZIP and loose XML, without extracting')
    zip_parser.add_argument('archive', type=Path)
    zip_parser.add_argument('--manifest', type=Path)
    zip_parser.add_argument('--scope', action='append', default=[])
    zip_parser.add_argument('--max-entry-mib', type=int, default=256)
    zip_parser.add_argument('--max-total-mib', type=int, default=512)
    zip_parser.add_argument('--max-entries', type=int, default=100_000)
    metadata_parser = sub.add_parser('metadata', help='compare manifest and textures.info paths')
    metadata_parser.add_argument('manifest', type=Path)
    metadata_parser.add_argument('textures', type=Path)
    for command in (zip_parser, metadata_parser):
        command.add_argument('--output', type=Path, help='write JSON atomically; default is stdout')
    args = parser.parse_args(argv)
    inputs = [args.manifest, args.textures] if args.command == 'metadata' else [args.archive, args.manifest]
    guard = Audit()
    try:
        if args.output is not None:
            for source in inputs:
                if source is not None and (args.output.resolve() == source.resolve()
                        or (args.output.exists() and source.exists() and os.path.samefile(args.output, source))):
                    raise ValueError('output must not overwrite an input or an alias of it')
    except (OSError, ValueError) as error:
        guard.add('output', error)
        print(json.dumps(guard.report, ensure_ascii=False, indent=2))
        return 1
    if args.command == 'metadata':
        report = audit_metadata(args.manifest, args.textures)
    else:
        report = audit_zip(args.archive, manifest=args.manifest, scopes=args.scope,
            max_entry_bytes=args.max_entry_mib * MIB,
            max_total_bytes=args.max_total_mib * MIB, max_entries=args.max_entries)
    content = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    temporary = None
    if args.output is None:
        print(content, end='')
    else:
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=args.output.parent,
                                             prefix='.audit-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content)
            os.replace(temporary, args.output)
        except OSError as error:
            guard.report = report
            guard.add('output', error)
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return {'passed': 0, 'failed': 1, 'incomplete': 2}[report['auditStatus']]


if __name__ == '__main__':
    raise SystemExit(main())
