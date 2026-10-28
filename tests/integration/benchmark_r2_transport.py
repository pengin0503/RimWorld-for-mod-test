"""Private identical-object transport comparison; only numeric summaries are public."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools import r2_assets as ra, codex_workflow as cw

PREFIX = 'Game-Linux/'
SAMPLE_BYTES = 2 * 1024 * 1024


def select_sample(items):
    small = [i for i in items if type(i.get('size')) is int and 0 < i['size'] <= 65536]
    version = [i for i in small if i['key'] == PREFIX + 'Version.txt']
    core = sorted((i for i in small if i['key'].startswith(PREFIX + 'Data/Core/Defs/')
                   and i['key'].endswith('.xml')), key=lambda i: i['key'])
    selected = version + core[:31]
    if (len(version) != 1 or len(selected) != 32
            or len({i['key'] for i in selected}) != 32
            or sum(i['size'] for i in selected) > SAMPLE_BYTES):
        raise ra.AssetError('bounded 32-object sample is unavailable')
    return selected


def safe_summary(data):
    if not isinstance(data, dict):
        data = {}
    trials = []
    raw = data.get('trials')
    for t in raw[:6] if isinstance(raw, list) else []:
        if (isinstance(t, dict) and t.get('transport') in ('cli', 'sdk')
                and type(t.get('seconds')) in (int, float) and 0 < t['seconds'] < 10**6):
            trials.append({'transport': t['transport'], 'seconds': t['seconds']})
    files, size = data.get('files'), data.get('bytesPerTrial')
    files = files if type(files) is int and 0 <= files <= 32 else 0
    size = size if type(size) is int and 0 <= size <= SAMPLE_BYTES else 0
    grouped = {mode: [t['seconds'] for t in trials if t['transport'] == mode] for mode in ('cli', 'sdk')}
    complete = all(len(v) == 3 for v in grouped.values())
    medians = {mode: statistics.median(v) for mode, v in grouped.items()} if complete else {}
    return {'files': files, 'bytesPerTrial': size, 'trials': trials,
            'medianSeconds': medians, 'hashesMatch': data.get('hashesMatch') is True,
            'ok': complete and files == 32 and size > 0 and data.get('hashesMatch') is True}


def benchmark(root, endpoint):
    with ra.R2(endpoint=endpoint, bucket='rimworld-17', transport='sdk') as client:
        items = select_sample(client.list_prefix(PREFIX))
    expected = None
    trials = []
    for trial, mode in enumerate(('cli', 'sdk', 'sdk', 'cli', 'cli', 'sdk')):
        dest = root / f'trial-{trial}'
        if dest.exists():
            raise ra.AssetError('benchmark requires fresh destinations')
        started = time.monotonic()
        with ra.R2(endpoint=endpoint, bucket='rimworld-17', transport=mode) as client:
            counts = cw._download(client, PREFIX, dest, items)
        elapsed = time.monotonic() - started
        if counts != {'downloaded': 32, 'cached': 0}:
            raise ra.AssetError('cached input contaminated the benchmark')
        hashes = [hashlib.sha256((dest / i['key'][len(PREFIX):]).read_bytes()).hexdigest() for i in items]
        if expected is not None and hashes != expected:
            raise ra.AssetError('transport comparison hash mismatch')
        expected = hashes
        trials.append({'transport': mode, 'seconds': round(elapsed, 6)})
    return safe_summary({'files': 32, 'bytesPerTrial': sum(i['size'] for i in items),
                         'trials': trials, 'hashesMatch': True})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('run', 'publish'))
    parser.add_argument('--root', required=True)
    args = parser.parse_args(argv)
    root = cw._safe_private(Path(args.root))
    summary = root / 'safe-benchmark.json'
    if args.phase == 'publish':
        try:
            data = json.loads(summary.read_text()) if summary.stat().st_size < 65536 else {}
        except (OSError, ValueError):
            data = {}
        print(json.dumps(safe_summary(data), allow_nan=False, indent=2))
        return 0
    summary.write_text(json.dumps(safe_summary({})))
    result = benchmark(root, os.environ.get('R2_ENDPOINT', ''))
    summary.write_text(json.dumps(result, allow_nan=False, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
