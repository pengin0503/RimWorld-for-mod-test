"""Codex Cloud private asset orchestration for the existing RimWorld test-only host.

No game binaries, Workshop content, MOD index or raw logs enter git.
The Controller/Worker remain the authority for validation semantics.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile, BadZipFile

try:
    from tools import r2_assets, validation_host, mod_load_plan
except ImportError:
    import r2_assets
    import validation_host
    import mod_load_plan

PRIVATE_INDEX_NAME = "mods.json"
PRIVATE_MOD_INDEX_OBJECT = r2_assets.PRIVATE_INDEX_KEY
WORKSHOP_ID = re.compile(r"[0-9]{1,20}\Z")


class WorkflowError(Exception):
    def __init__(self, detail, code="workflowError"):
        self.code = code
        super().__init__(detail)


def _safe_private(root: Path) -> Path:
    raw = Path(root).expanduser().absolute()
    if any(part.is_symlink() for part in (raw, *raw.parents)):
        raise WorkflowError("private work root has a symbolic-link component")
    root = raw.resolve()
    # Restrict the real project checkout, not unrelated sandbox .git ancestors.
    checkout = Path(__file__).resolve().parents[1]
    if root == checkout or checkout in root.parents or (root / ".git").exists():
        raise WorkflowError("private work root must be outside the project checkout")
    if root.exists() and not root.is_dir():
        raise WorkflowError("private work root is not a directory")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    return root


def load_index(archive: Path) -> dict:
    """Read only mods.json from a private ZIP without extracting ZIP paths."""
    archive = Path(archive)
    try:
        if archive.stat().st_size > 15 * 1024 * 1024:
            raise WorkflowError("private index archive exceeds 15 MiB")
        with ZipFile(archive) as z:
            names = [n for n in z.namelist() if n == PRIVATE_INDEX_NAME or n.endswith("/" + PRIVATE_INDEX_NAME)]
            if len(names) != 1:
                raise WorkflowError("private index ZIP must contain exactly one mods.json")
            member = z.getinfo(names[0])
            if member.file_size > 25 * 1024 * 1024:
                raise WorkflowError("uncompressed index exceeds 25 MiB")
            data = json.loads(z.read(member).decode("utf-8"))
    except (OSError, BadZipFile, ValueError, UnicodeError, KeyError) as error:
        raise WorkflowError("cannot load private MOD index ZIP") from error
    if not isinstance(data, dict) or not isinstance(data.get("mods"), list):
        raise WorkflowError("unsupported MOD index schema")
    schema = data.get("schema_version")
    if not ((type(schema) is int and schema == 1) or (type(schema) is str and schema == "1")):
        raise WorkflowError("unsupported MOD index schema")
    return data


def resolve(index: dict, identifier: str) -> dict:
    """Only match exact Workshop ID, packageId or name, never descriptions."""
    needle = identifier.casefold()
    matches = [m for m in index["mods"] if isinstance(m, dict) and any(
        isinstance(m.get(field), str) and m[field].casefold() == needle
        for field in ("workshop_id", "package_id", "name"))]
    if not matches:
        raise WorkflowError(f"no exact index match for {identifier!r}")
    if len(matches) > 1:
        raise WorkflowError(f"ambiguous MOD identifier {identifier!r} ({len(matches)} matches)")
    mod = matches[0]
    if not WORKSHOP_ID.fullmatch(str(mod.get("workshop_id", ""))):
        raise WorkflowError("index contains an unsafe Workshop ID")
    return {"workshopId": mod["workshop_id"], "packageId": mod.get("package_id", ""),
            "name": mod.get("name", ""), "supportedVersions": mod.get("supported_versions", [])}


def lookup(index: dict, query: str, *, exact: bool = False, limit: int = 20) -> dict:
    if limit < 1 or limit > 100:
        raise WorkflowError("limit must be between 1 and 100")
    needle = query.casefold()
    results = []
    for mod in index["mods"]:
        if not isinstance(mod, dict):
            continue
        values = [mod.get(k, "") for k in ("workshop_id", "package_id", "name")]
        valid = [v.casefold() for v in values if isinstance(v, str)]
        matched = needle in valid if exact else any(needle in v for v in valid)
        if matched:
            results.append({"workshopId": mod.get("workshop_id"),
                            "packageId": mod.get("package_id"), "name": mod.get("name"),
                            "supportedVersions": mod.get("supported_versions", [])})
    return {"total": len(results), "truncated": len(results) > limit, "mods": results[:limit]}


def r2_client(aws: str) -> r2_assets.R2:
    return r2_assets.R2(endpoint=os.environ.get("R2_ENDPOINT", ""),
                        bucket=os.environ.get("R2_BUCKET", "rimworld-17"), aws=aws)


def _fetch(r2: r2_assets.R2, prefix: str, dest: Path, *, runtime=False,
           include=None, refresh=False) -> dict:
    listed = r2.list_prefix(prefix)
    items = listed
    if runtime:
        items = [item for item in items if game_runtime_asset(item["key"])]
    if include is not None:
        items = [item for item in items if include(item["key"])]
    counts = _selection_counts(listed, items)
    counts.update(_download(r2, prefix, dest, items, refresh=refresh))
    return counts


def _selection_counts(listed: list[dict], items: list[dict]) -> dict:
    if not items:
        raise WorkflowError("requested R2 prefix has no matching files")
    size = sum(item["size"] for item in items)
    if len(items) > r2_assets.MAX_OBJECTS or size > r2_assets.MAX_BYTES:
        raise WorkflowError("R2 selection exceeds safety caps; narrow the request")
    return {"selected": len(items), "skipped": len(listed) - len(items),
            "listedBytes": size, "downloaded": 0, "cached": 0}


def _download(r2: r2_assets.R2, prefix: str, dest: Path, items: list[dict], *, refresh=False) -> dict:
    counts = {"downloaded": 0, "cached": 0}
    if not items:
        return counts
    # AWS CLI get-object is one subprocess per object; bounded parallelism avoids
    # a multi-hour sequential download while keeping R2 requests scoped.
    with ThreadPoolExecutor(max_workers=min(4, len(items))) as pool:
        jobs = []
        for item in items:
            relative = item["key"][len(prefix):]
            dest_file = r2_assets.ensure_safe_destination(dest, relative)
            jobs.append(pool.submit(r2.get, item["key"], dest_file, item["size"], refresh=refresh))
        for job in as_completed(jobs):
            counts[job.result()] += 1
    return counts


def _check_cached_inputs(destination: Path, items: list[dict], prefix: str, folders: list[str]):
    """Do not let stale files or even empty version directories change game selection."""
    files = {item["key"][len(prefix):] for item in items}
    dirs = {""}
    for relative in files | set(folders):
        path = Path(relative)
        dirs.update(p.as_posix() for p in path.parents if p.as_posix() != ".")
    dirs.update(folders)
    if not destination.exists():
        return
    for path in destination.rglob("*"):
        relative = path.relative_to(destination).as_posix()
        if path.is_symlink() or (path.is_file() and relative not in files) or (path.is_dir() and relative not in dirs):
            raise WorkflowError("Cached MOD has inputs outside the resolved plan; use a fresh private root", "unexpectedCachedModInputs")


def game_runtime_asset(key: str) -> bool:
    """Keep all runtime/native/asset files, omit *.debug and other languages' tarballs."""
    r2_assets.validate_key(key)
    if not key.startswith("Game-Linux/"):
        raise WorkflowError("game runtime selection requires Game-Linux/")
    rel = key[len("Game-Linux/"):]
    if rel.lower().endswith(".debug"):
        return False
    parts = rel.split("/")
    for pos, item in enumerate(parts):
        if item.lower() == "languages" and len(parts) > pos + 1:
            following = parts[pos + 1]
            if following.lower().endswith(".tar"):
                return following.casefold().startswith(("english", "japanese"))
    return True



def mod_validation_asset(key: str, *, folders: list[str], language: str = "English") -> bool:
    """Filter only within the already resolved effective game load folders."""
    r2_assets.validate_key(key)
    if not key.startswith("Workshop/"):
        raise WorkflowError("MOD selection requires Workshop/<ID>/")
    relative = key.split("/", 2)[2]
    return relative.casefold() in {"about/about.xml", "loadfolders.xml"} or mod_load_plan.select_asset(relative, folders, language)


def prepare(args) -> dict:
    root = _safe_private(args.private_root)
    game, snapshot = root / "game-source", root / "game-snapshot"
    if snapshot.exists():
        if args.refresh:
            raise WorkflowError("snapshot is immutable; choose a new --private-root for a changed game build")
        info = validation_host.load_snapshot(snapshot)
        return {"status": "snapshotReused", "version": info["version"], "adapter": info["adapter"]}
    if game.is_symlink():
        raise WorkflowError("game source cannot be a symlink")
    game.mkdir(mode=0o700, exist_ok=True)
    counts = _fetch(r2_client(args.aws), "Game-Linux/", game, runtime=True, refresh=args.refresh)
    if not (game / "Version.txt").is_file():
        raise WorkflowError("game Version.txt missing after R2 download")
    try:
        info = validation_host.prepare_game(game, snapshot, log=lambda _message: None)
    except validation_host.Blocked as exc:
        raise WorkflowError(f"game snapshot blocked: {exc.code}") from exc
    return {"status": "prepared", "version": info["version"], "adapter": info["adapter"],
            "files": info["fileCount"], "r2": counts}


def private_index(args, root: Path) -> Path:
    if args.index_zip:
        return Path(args.index_zip).expanduser().absolute()
    archive = root / "private-index" / Path(PRIVATE_MOD_INDEX_OBJECT).name
    r2_client(args.aws).get(PRIVATE_MOD_INDEX_OBJECT, archive, expected_size=None, refresh=args.refresh)
    return archive


def _local_files(root: Path) -> list[str]:
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise WorkflowError("local MOD contains a symbolic link", "invalidLocalMod")
        if path.is_file():
            files.append(path.relative_to(root).as_posix())
    return files


def _local_metadata(root: Path):
    raw = Path(root).expanduser().absolute()
    if any(part.is_symlink() for part in (raw, *raw.parents)) or not raw.is_dir():
        raise WorkflowError("local MOD must be a real directory", "invalidLocalMod")
    files = _local_files(raw)
    abouts = [f for f in files if f.casefold() == "about/about.xml"]
    configs = [f for f in files if f.casefold() == "loadfolders.xml"]
    if len(abouts) != 1 or len(configs) > 1:
        raise WorkflowError("Missing or ambiguous MOD metadata", "invalidModMetadata")
    try:
        meta = mod_load_plan.parse_xml((raw / abouts[0]).read_bytes())
    except mod_load_plan.LoadPlanError as exc:
        raise WorkflowError(str(exc), exc.code) from exc
    package_id = (meta.findtext("packageId") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.]+", package_id):
        raise WorkflowError("local MOD has no usable packageId", "invalidModMetadata")
    return raw, files, configs, meta, package_id


def local_mod_plan(root: Path, active: set) -> dict:
    """Plan a MOD built outside R2 (e.g. the user's own repository) with the same rules."""
    raw, files, configs, meta, package_id = _local_metadata(root)
    active = set(active) | {package_id.casefold()}
    try:
        missing = mod_load_plan.missing_dependencies(meta, active)
        if missing:
            raise WorkflowError("Missing required dependencies: " + ", ".join(missing), "missingDependencies")
        config = (raw / configs[0]).read_bytes() if configs else None
        folders = mod_load_plan.load_folders(files, config, active)
    except mod_load_plan.LoadPlanError as exc:
        raise WorkflowError(str(exc), exc.code) from exc
    return {"path": str(raw), "packageId": package_id, "loadFolders": folders}


def resolve_mod_graph(index, roots, read_metadata, *, official=None, local=None):
    """Resolve metadata recursively and return a deterministic dependency order."""
    official = set(official or {'ludeon.rimworld'})
    official_names = {'ludeon.rimworld': 'Core', 'ludeon.rimworld.royalty': 'Royalty',
                      'ludeon.rimworld.ideology': 'Ideology', 'ludeon.rimworld.biotech': 'Biotech',
                      'ludeon.rimworld.odyssey': 'Odyssey'}
    nodes, edges, queue = {}, {}, list(roots)
    def by_package(package):
        if local and local["packageId"].casefold() == package.casefold():
            return local
        found = [m for m in index.get('mods', []) if isinstance(m.get('package_id'), str)
                 and m['package_id'].casefold() == package.casefold()]
        if not found:
            raise WorkflowError(f'dependency package {package} missing from private index', 'missingDependencies')
        if len(found) != 1:
            raise WorkflowError(f'dependency package {package} ambiguous in private index', 'dependencyUnresolved')
        return resolve(index, found[0]['workshop_id'])
    while queue:
        package = queue.pop(0).casefold()
        if package in nodes or package in official:
            continue
        if package in official_names:
            raise WorkflowError(f'official content required: add {official_names[package]} to --official', 'officialContentMissing')
        if len(nodes) >= 1000:
            raise WorkflowError('dependency graph exceeds 1000 MODs', 'dependencyLimit')
        mod = by_package(package)
        meta = read_metadata(mod)
        actual = (meta.findtext('packageId') or '').strip().casefold()
        if actual != package:
            raise WorkflowError('private index and MOD metadata disagree on packageId', 'packageIdMismatch')
        try:
            required = mod_load_plan.missing_dependencies(meta, set())
        except mod_load_plan.LoadPlanError as error:
            raise WorkflowError(str(error), error.code) from error
        nodes[package] = mod
        edges.setdefault(package, set())
        for dep in required:
            dep = dep.casefold()
            if dep not in official:
                queue.append(dep)
                edges[package].add(dep)
        for tag, reverse in (('loadAfter', False), ('loadBefore', True)):
            sections = meta.findall(tag)
            if len(sections) > 1:
                raise WorkflowError(f'duplicate {tag}', 'invalidDependencies')
            for section in sections:
                for item in section:
                    value = (item.text or '').strip().casefold()
                    if item.tag != 'li' or not re.fullmatch(r'[a-z0-9_.]+', value):
                        raise WorkflowError(f'invalid {tag} entry', 'invalidDependencies')
                    if value not in official:
                        queue.append(value)
                        if reverse:
                            edges.setdefault(value, set()).add(package)
                        else:
                            edges[package].add(value)
    ordered = []
    while nodes:
        ready = [key for key in nodes if not (edges.get(key, set()) & nodes.keys())]
        if not ready:
            raise WorkflowError('dependency order has a cycle', 'dependencyCycle')
        for key in ready:
            ordered.append(nodes.pop(key))
    return ordered


def fetch_mods(args) -> dict:
    root = _safe_private(args.private_root)
    local_target = getattr(args, "local_target", None)
    if bool(args.target) == bool(local_target):
        raise WorkflowError("give exactly one of --target or --local-target", "invalidTarget")
    local_id = _local_metadata(local_target)[4] if local_target else None
    index = load_index(private_index(args, root))
    selected = [resolve(index, name) for name in list(args.dependency or []) + ([args.target] if args.target else [])]
    if any(not m["packageId"] for m in selected):
        raise WorkflowError("index has no packageId for a selected MOD")
    ids = [m["workshopId"] for m in selected]
    if len(ids) != len(set(ids)):
        raise WorkflowError("same Workshop MOD appears as target and dependency")
    if local_id and local_id.casefold() in {m["packageId"].casefold() for m in selected}:
        raise WorkflowError("local MOD repeats a MOD selected from the index", "duplicateMod")
    if (root / "request.json").exists():
        raise WorkflowError("request.json exists; preserve edits and use a new private root")
    official = getattr(args, "official", None) or ["Core"]
    allowed = {"Core", "Royalty", "Ideology", "Biotech", "Odyssey"}
    if not official or official[0] != "Core" or len(set(official)) != len(official) or set(official)-allowed:
        raise WorkflowError("official must begin with Core and contain supported unique DLCs", "invalidOfficialContent")
    official_ids = {"ludeon.rimworld" if n == "Core" else "ludeon.rimworld." + n.casefold() for n in official}
    target_package = selected[-1]["packageId"].casefold() if not local_target else local_id.casefold()
    r2 = r2_client(args.aws)
    fetched = []
    prepared_by_id = {}
    def read_metadata(mod):
        if mod["workshopId"] is None:
            return _local_metadata(local_target)[3]
        destination = root / "mods" / mod["workshopId"]
        prefix = f"Workshop/{mod['workshopId']}/"
        listed = r2.list_prefix(prefix)
        metadata = [item for item in listed if item["key"][len(prefix):].casefold() in {"about/about.xml", "loadfolders.xml"}]
        abouts = [item for item in metadata if item["key"][len(prefix):].casefold() == "about/about.xml"]
        configs = [item for item in metadata if item["key"][len(prefix):].casefold() == "loadfolders.xml"]
        if len(abouts) != 1 or len(configs) > 1:
            raise WorkflowError("Missing or ambiguous MOD metadata", "invalidModMetadata")
        if any(item["size"] > 4*1024*1024 for item in metadata):
            raise WorkflowError("MOD metadata exceeds 4 MiB", "metadataTooLarge")
        counts = _download(r2, prefix, destination, metadata, refresh=args.refresh)
        try:
            meta = mod_load_plan.parse_xml((destination / abouts[0]["key"][len(prefix):]).read_bytes())
        except mod_load_plan.LoadPlanError as exc:
            raise WorkflowError(str(exc), exc.code) from exc
        prepared_by_id[mod["workshopId"]] = (mod, destination, prefix, listed, metadata, counts, configs)
        return meta
    roots = [m["packageId"] for m in selected]
    local_node = None
    if local_target:
        local_node = {"packageId": local_id, "workshopId": None, "name": "local target"}
        roots.append(local_id)
    graph = resolve_mod_graph(index, roots, read_metadata, official=official_ids, local=local_node)
    selected = [m for m in graph if m["workshopId"] is not None]
    active = {m["packageId"].casefold() for m in graph} | official_ids
    prepared = []
    for mod in selected:
        mod, destination, prefix, listed, metadata, counts, configs = prepared_by_id[mod["workshopId"]]
        try:
            config = (destination / configs[0]["key"][len(prefix):]).read_bytes() if configs else None
            folders = mod_load_plan.load_folders([i["key"][len(prefix):] for i in listed], config, active)
        except mod_load_plan.LoadPlanError as exc:
            raise WorkflowError(str(exc), exc.code) from exc
        prepared.append((mod, destination, prefix, listed, metadata, counts, folders))
    local = local_mod_plan(local_target, active) if local_target else None
    for mod, destination, prefix, listed, metadata, counts, folders in prepared:
        metadata_keys = {i["key"] for i in metadata}
        items = [i for i in listed if args.scope == "all" or i["key"] in metadata_keys or
                 mod_validation_asset(i["key"], folders=folders, language=args.language)]
        summary = _selection_counts(listed, items)
        _check_cached_inputs(destination, items, prefix, folders)
        summary.update(counts)
        # Retain chosen directories even if no loader file survives filtering.
        for folder in folders:
            r2_assets.ensure_safe_destination(destination, folder).mkdir(parents=True, exist_ok=True)
        payload = [i for i in items if i["key"] not in metadata_keys]
        for outcome, count in _download(r2, prefix, destination, payload, refresh=args.refresh).items():
            summary[outcome] += count
        fetched.append({"workshopId": mod["workshopId"], "name": mod["name"],
                        "r2": summary, "scope": args.scope, "loadFolders": folders})
    # The Controller compares these with the folders the game actually loaded.
    planned = {item["workshopId"]: item["loadFolders"] for item in fetched}
    mods = []
    for m in graph:
        if m["workshopId"] is None:
            mods.append({"path": local["path"], "packageId": local["packageId"], "target": True,
                         "expectedLoadFolders": local["loadFolders"]})
        else:
            mods.append({"path": str((root / "mods" / m["workshopId"]).absolute()),
                         "packageId": m["packageId"], "target": local is None and m["packageId"].casefold() == target_package,
                         "expectedLoadFolders": planned[m["workshopId"]]})
    request = {"recordType": "modValidationRequest", "schemaVersion": 1,
               "levels": ["A"], "official": official, "language": args.language,
               "mods": mods, "expectations": {}}
    req_path = root / "request.json"
    req_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(req_path, 0o600)
    return {"status": "modsReady", "fetched": fetched, "local": local, "request": str(req_path),
            "validationLevel": "A",
            "note": "Load folders and required dependencies checked against the complete request; "
                    "resources outside loader inputs still require explicit retrieval"}


@contextmanager
def _no_cloud_credentials():
    """Do not hand R2/AWS secrets to untrusted MOD DLL code in the Worker."""
    names = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
             "AWS_PROFILE", "AWS_DEFAULT_PROFILE", "R2_ENDPOINT", "R2_BUCKET")
    saved = {k: os.environ[k] for k in names if k in os.environ}
    for key in names:
        os.environ.pop(key, None)
    try:
        yield
    finally:
        for key in names:
            os.environ.pop(key, None)
        os.environ.update(saved)


def validate(args) -> dict:
    root = _safe_private(args.private_root)
    snapshot = root / "game-snapshot"
    if not snapshot.exists():
        raise WorkflowError("no snapshot; run prepare first")
    request = Path(args.request or root / "request.json").expanduser().absolute()
    if not request.is_file():
        raise WorkflowError("request JSON missing; run fetch-mods or supply --request")
    if not Path(args.worker).exists():
        raise WorkflowError("built Worker missing; run dotnet build")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", args.run_id):
        raise WorkflowError("invalid run ID")
    out = root / "results" / args.run_id
    if out.parent.is_symlink():
        raise WorkflowError("result directory cannot be a symlink")
    if out.exists():
        raise WorkflowError("result directory already exists; use a new --run-id")
    with _no_cloud_credentials():
        result = validation_host.run_validation(snapshot, request, out, args.worker,
                                                baseline_cache=root / "baseline-cache",
                                                hash_cache=root / "hash-cache.json")
    return {"status": result.get("status"),
            "reasons": [r.get("code") for r in result.get("reasons", [])],
            "result": str(out / "result.json"),
            "scope": result.get("scope", {}).get("notChecked", [])}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    s = commands.add_parser("search", help="search private MOD index ZIP without extraction")
    s.add_argument("--index-zip", required=True)
    s.add_argument("query")
    s.add_argument("--exact", action="store_true")
    s.add_argument("--limit", type=int, default=20)
    for name in ("prepare", "fetch-mods", "validate"):
        sub = commands.add_parser(name)
        sub.add_argument("--private-root", required=True)
        if name != "validate":
            sub.add_argument("--aws", default=os.environ.get("AWS_CLI_PATH", "aws"))
            sub.add_argument("--refresh", action="store_true")
        if name == "fetch-mods":
            sub.add_argument("--index-zip")
            sub.add_argument("--target", help="target MOD from the private index")
            sub.add_argument("--local-target", help="target MOD folder built locally (not fetched from R2)")
            sub.add_argument("--dependency", action="append", default=[])
            sub.add_argument("--language", default="English")
            sub.add_argument("--scope", choices=("validation", "all"), default="validation")
            sub.add_argument("--official", nargs="+", default=["Core"], help="Core followed by requested official DLCs")
        if name == "validate":
            sub.add_argument("--request")
            sub.add_argument("--worker", default="worker/bin")
            sub.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "search":
            output = lookup(load_index(Path(args.index_zip)), args.query, exact=args.exact, limit=args.limit)
        elif args.command == "prepare":
            output = prepare(args)
        elif args.command == "fetch-mods":
            output = fetch_mods(args)
        else:
            output = validate(args)
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
        return {"passed": 0, "failed": 1, "blocked": 2, "incomplete": 3}.get(output.get("status"), 0)
    except validation_host.Blocked as exc:
        print(json.dumps({"status": "blocked", "error": exc.code}), file=sys.stderr)
        return 2
    except (WorkflowError, r2_assets.AssetError, OSError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "code": getattr(exc, "code", "workflowError"), "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
