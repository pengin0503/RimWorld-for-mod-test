"""Private, main-bound acquisition for the C reference metadata audit."""
import hashlib
import shutil
import time
from pathlib import Path
from tools import codex_workflow as cw, private_validation as pv, validation_host as vh

ADAPTER = vh.ADAPTERS['rimworld-1.7.4985-rev1269']
EXPECTED = {**ADAPTER['sha256'], **ADAPTER['qualified'][('linux-x64', 'waylith')]['runtimeSha256']}
VERSION = '1.7.4985 rev1269'


def verify_directory(directory):
    directory = Path(directory)
    try:
        if directory.is_symlink() or (directory/'Version.txt').is_symlink(): return False
        version = directory/'Version.txt'
        if version.stat().st_size > 128 or version.read_text().removesuffix('\n').removesuffix('\r') != VERSION: return False
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
    manifest = {**identity, 'verified': False}
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
                matches = [x for x in client.list_prefix(key) if x.get('key') == key]
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
    if session.is_symlink() or manifest_file.is_symlink() or not manifest_file.is_file() or manifest_file.stat().st_size > 65536:
        raise ValueError('invalid audit manifest')
    manifest = pv.read_json(manifest_file)
    if not isinstance(manifest, dict) or any(manifest.get(k) != v for k, v in identity.items()) or manifest.get('verified') is not True or manifest.get('invalidated') is True or not verify(root):
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


def public_summary(raw, identity):
    raw = raw if isinstance(raw, dict) else {}
    bound = all(raw.get(k) == v for k, v in identity.items())
    return {**identity, 'verified': bound and raw.get('verified') is True,
            'staticAuditStatus': 'incomplete', 'c0Passed': False, 'types': []}
