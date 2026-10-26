"""Codex Cloud private asset orchestration for the existing RimWorld test-only host.

No game binaries, Workshop content, MOD index or raw logs enter git.
The Controller/Worker remain the authority for validation semantics.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import sys
from zipfile import ZipFile, BadZipFile

try:
    from tools import r2_assets, validation_host
except ImportError:
    import r2_assets
    import validation_host

PRIVATE_INDEX_NAME = "mods.json"
PRIVATE_MOD_INDEX_OBJECT = "PrivateIndex/rimworld-mod-index-2026-10-26.zip"
WORKSHOP_ID = re.compile(r"[0-9]{1,20}\Z")


class WorkflowError(Exception):
    pass


def _safe_private(root: Path) -> Path:
    root = Path(root).expanduser().absolute()
    if root.is_symlink():
        raise WorkflowError("private work root cannot be a symbolic link")
    if any((parent / ".git").exists() for parent in (root, *root.parents)):
        raise WorkflowError("private work root must be outside the Git checkout")
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
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("mods"), list):
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


def _fetch(r2: r2_assets.R2, prefix: str, dest: Path, *, runtime=False, refresh=False) -> dict:
    items = r2.list_prefix(prefix)
    if runtime:
        items = [item for item in items if game_runtime_asset(item["key"])]
    if not items:
        raise WorkflowError("requested R2 prefix has no matching files")
    size = sum(item["size"] for item in items)
    if len(items) > r2_assets.MAX_OBJECTS or size > r2_assets.MAX_BYTES:
        raise WorkflowError("R2 selection exceeds safety caps; narrow the request")
    counts = {"selected": len(items), "listedBytes": size, "downloaded": 0, "cached": 0}
    for item in items:
        relative = item["key"][len(prefix):]
        dest_file = r2_assets.ensure_safe_destination(dest, relative)
        outcome = r2.get(item["key"], dest_file, item["size"], refresh=refresh)
        counts[outcome] += 1
    return counts


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
    archive = root / "private-index" / "rimworld-mod-index-2026-10-26.zip"
    r2_client(args.aws).get(PRIVATE_MOD_INDEX_OBJECT, archive, expected_size=None, refresh=args.refresh)
    return archive


def fetch_mods(args) -> dict:
    root = _safe_private(args.private_root)
    index = load_index(private_index(args, root))
    selected = [resolve(index, name) for name in list(args.dependency or []) + [args.target]]
    if any(not m["packageId"] for m in selected):
        raise WorkflowError("index has no packageId for a selected MOD")
    ids = [m["workshopId"] for m in selected]
    if len(ids) != len(set(ids)):
        raise WorkflowError("same Workshop MOD appears as target and dependency")
    if (root / "request.json").exists():
        raise WorkflowError("request.json exists; preserve edits and use a new private root")
    fetched = []
    r2 = r2_client(args.aws)
    for mod in selected:
        destination = root / "mods" / mod["workshopId"]
        summary = _fetch(r2, f"Workshop/{mod['workshopId']}/", destination, refresh=args.refresh)
        if not (destination / "About" / "About.xml").is_file():
            raise WorkflowError("selected MOD is missing About/About.xml")
        fetched.append({"workshopId": mod["workshopId"], "name": mod["name"], "r2": summary})
    mods = [{"path": str((root / "mods" / m["workshopId"]).absolute()),
             "packageId": m["packageId"], "target": m is selected[-1]} for m in selected]
    request = {"recordType": "modValidationRequest", "schemaVersion": 1,
               "levels": ["A"], "official": ["Core"], "language": args.language,
               "mods": mods, "expectations": {}}
    req_path = root / "request.json"
    req_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(req_path, 0o600)
    return {"status": "modsReady", "fetched": fetched, "request": str(req_path),
            "validationLevel": "A",
            "note": "Check dependency order, DLCs and level B expectations before running"}


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
    out = root / "results" / args.run_id
    if out.exists():
        raise WorkflowError("result directory already exists; use a new --run-id")
    result = validation_host.run_validation(snapshot, request, out, args.worker,
                                            baseline_cache=root / "baseline-cache")
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
            sub.add_argument("--target", required=True)
            sub.add_argument("--dependency", action="append", default=[])
            sub.add_argument("--language", default="English")
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
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
