"""Development-only native FICLONE measurement on a dedicated Linux filesystem.

Self-made bytes only. FIEMAP data-extent union excludes filesystem metadata.
Times include the product's SHA256 verification; no claim about cold disks.
"""
import argparse
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import struct
import sys
import tempfile
import time
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from tools import validation_host as vh


def union_bytes(ranges):
    end, total = 0, 0
    for physical, length in sorted(ranges):
        if physical <= 0 or length <= 0:
            raise ValueError('unmapped physical range')
        total += max(0, physical + length - max(end, physical))
        end = max(end, physical + length)
    return total


def extent_ranges(data):
    if len(data) < 32:
        raise ValueError('missing FIEMAP header')
    count, capacity = struct.unpack_from('II', data, 20)
    if not 0 < count <= capacity or len(data) < 32 + count * 56:
        raise ValueError('incomplete FIEMAP')
    result = []
    last = False
    for i in range(count):
        logical, physical, length, _, _, flags = struct.unpack_from('QQQQQI', data, 32 + i * 56)
        # Unknown/delayed/encoded/inline/unwritten physical storage is not measurable here.
        if flags & (0x2 | 0x4 | 0x8 | 0x80 | 0x100 | 0x200 | 0x800) or not physical or not length:
            raise ValueError('unsupported physical extent')
        result.append((physical, length))
        last = bool(flags & 1)
    if not last:
        raise ValueError('FIEMAP capacity exceeded')
    return result


def physical_ranges(path):
    import fcntl
    data = bytearray(32 + 512 * 56)
    struct.pack_into('QQIIII', data, 0, 0, 2**64 - 1, 1, 0, 512, 0)  # FIEMAP_FLAG_SYNC
    with path.open('rb') as stream:
        fcntl.ioctl(stream.fileno(), 0xC020660B, data, True)
    return extent_ranges(data)


def hashes(source):
    return {p.name: vh.sha256_file(p) for p in sorted(source.iterdir())}


def stage(source, dest, expected, *, force_copy=False):
    dest.mkdir()
    modes = {'copy': 0, 'reflink': 0}
    # Only the transport is disabled for the control; the product still hashes and verifies.
    with patch.object(vh, '_clone_mod_file', return_value=False) if force_copy else nullcontext():
        for name, digest in expected.items():
            modes[vh.copy_verified_mod_file(source / name, dest / name, digest)] += 1
    return modes


def isolated(source, baseline, target, expected):
    name = next(iter(expected))
    paths = [root / name for root in (source, baseline, target)]
    if len({(p.stat().st_dev, p.stat().st_ino) for p in paths}) != 3:
        return False
    old = [p.read_bytes() for p in paths]
    with paths[1].open('r+b') as f: f.write(bytes([old[1][0] ^ 255]))
    first = paths[0].read_bytes() == old[0] and paths[2].read_bytes() == old[2]
    with paths[2].open('r+b') as f:
        f.seek(1); f.write(bytes([old[2][1] ^ 255]))
    return first and paths[0].read_bytes() == old[0] and paths[1].read_bytes()[1:] == old[1][1:]


def measure(root, repeats=5):
    if root.exists():
        raise ValueError('root must be new')
    root.mkdir(parents=True)
    source = root / 'source'; source.mkdir()
    # 4 large + 512 small files, random and incompressible. Same files for every run.
    for i in range(4):
        with (source / f'large-{i}').open('wb') as f:
            for _ in range(32): f.write(os.urandom(1024 * 1024))
    for i in range(512): (source / f'small-{i}').write_bytes(os.urandom(32 * 1024))
    expected = hashes(source)
    os.sync()
    original_ranges = [r for p in source.iterdir() for r in physical_ranges(p)]
    original_bytes = union_bytes(original_ranges)
    rows = []
    for repeat in range(repeats):
        for mode in (['copy', 'reflink'] if repeat % 2 == 0 else ['reflink', 'copy']):
            run = root / f'{repeat}-{mode}'; run.mkdir()
            started = time.monotonic()
            a = stage(source, run / 'baseline', expected, force_copy=mode == 'copy')
            b = stage(source, run / 'target', expected, force_copy=mode == 'copy')
            seconds = time.monotonic() - started
            os.sync()  # outside timing; FIEMAP after persistence
            union = union_bytes(original_ranges + [r for sub in ('baseline', 'target')
                for p in (run / sub).iterdir() for r in physical_ranges(p)])
            independent = isolated(source, run / 'baseline', run / 'target', expected)
            rows.append({'repeat': repeat + 1, 'mode': mode, 'seconds': round(seconds, 6),
                'modes': {k: a[k] + b[k] for k in a}, 'additionalDataBytes': union - original_bytes,
                'independent': independent})
            shutil.rmtree(run); os.sync()
    # A real cross-device clone must fall back and verify, not silently count as COW.
    with tempfile.TemporaryDirectory() as temporary:
        cross = Path(temporary) / 'source'; cross.write_bytes(b'cross-device-owned-fixture')
        cross_different = cross.stat().st_dev != root.stat().st_dev
        fallback = vh.copy_verified_mod_file(cross, root / 'cross', vh.sha256_file(cross))
    stale_detected = True
    for forced in (True, False):
        try:
            with patch.object(vh, '_clone_mod_file', return_value=False) if forced else nullcontext():
                vh.copy_verified_mod_file(source / 'small-0', root / f'stale-{forced}', '0' * 64)
        except vh.Blocked as e: stale_detected &= e.code == 'modChanged'
        else: stale_detected = False
    expected_count = len(expected) * 2
    ok = (cross_different and fallback == 'copy' and stale_detected
          and all(r['independent'] and r['modes'][r['mode']] == expected_count for r in rows)
          and all(r['additionalDataBytes'] == 0 for r in rows if r['mode'] == 'reflink')
          and all(r['additionalDataBytes'] >= original_bytes * 2 for r in rows if r['mode'] == 'copy'))
    medians = {m: statistics.median(r['seconds'] for r in rows if r['mode'] == m) for m in ('copy', 'reflink')}
    return {'ok': ok, 'filesystem': 'dedicated-btrfs', 'files': len(expected), 'sourceDataBytes': original_bytes,
        'rows': rows, 'medianSeconds': medians, 'crossDeviceFallback': cross_different and fallback == 'copy',
        'staleHashesRejected': stale_detected, 'warmCache': True, 'metadataIncluded': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--summary', type=Path, required=True)
    args = p.parse_args()
    summary = measure(args.root.resolve())
    args.summary.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))
    return 0 if summary['ok'] else 1

if __name__ == '__main__': raise SystemExit(main())
