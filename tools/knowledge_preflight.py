"""Offline, version-pinned RimWorld knowledge checks. No network or game binaries.

Knowledge packs contain only evidence-backed names and documented relationships.
A partial catalog is OPEN-WORLD: an absent symbol is 'unknown', never 'missing'.
A successful static scan is never a qualified game/Worker validation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

try:
    from . import mod_load_plan
except ImportError:
    import mod_load_plan


PINNED_BUILD = "1.7.4985 rev1269"
BUNDLED_PACKS = {PINNED_BUILD: "1.7.4985-rev1269"}
DATABASE_ROOT = Path(__file__).resolve().parent.parent / "validation-data"
COLLECTIONS = {"type": "types", "method": "methods", "field": "fields",
               "def": "defs", "harmony": "harmony", "official": "official",
               "issue": "issues"}
SYMBOL = re.compile(r"[A-Za-z_][A-Za-z0-9_.:-]{0,255}\Z")
PACKAGE_ID = re.compile(r"[A-Za-z0-9_.]{1,160}\Z")
MAX_RECORD_BYTES = 2 * 1024 * 1024
MAX_FILES = 20_000
MAX_INPUT_BYTES = 128 * 1024 * 1024
MAX_XML_BYTES = 4 * 1024 * 1024
MAX_SCAN_XML_BYTES = 32 * 1024 * 1024


class KnowledgeError(ValueError):
    """Unknown/invalid/untrustworthy knowledge pack. Fail closed."""


class KnowledgeDatabase:
    def __init__(self, metadata: dict, collections: dict):
        self.metadata = metadata
        self.collections = collections

    def query(self, kind: str, symbol: str, *, parameters=None) -> dict:
        if kind not in COLLECTIONS or not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol):
            raise KnowledgeError("invalid knowledge query")
        if parameters is not None:
            if kind not in {"method", "harmony"}:
                raise KnowledgeError("only method/Harmony requirements can specify arguments")
            if (not isinstance(parameters, list) or len(parameters) > 24
                    or any(not isinstance(p, str) or
                           not re.fullmatch(r"[\x21-\x7e]{1,200}", p) for p in parameters)):
                raise KnowledgeError("invalid required method arguments")
        evidence = self.collections[kind].get(symbol)
        known = evidence is not None and (
            parameters is None or evidence.get("parameters") == parameters
        )
        result = {
            "recordType": "offlineKnowledgeQuery",
            "gameBuild": self.metadata["gameBuild"],
            "kind": kind,
            "symbol": symbol,
            "status": "present" if known else "unknown",
            "source": evidence["source"] if evidence is not None else None,
            "runtimeVerified": False,
            "catalogCoverage": "partial",
        }
        if evidence is not None and "parameters" in evidence:
            result["parameters"] = list(evidence["parameters"])
        return result


def _read_json(path: Path):
    if not path.is_file() or path.is_symlink():
        raise KnowledgeError("knowledge record missing or linked")
    size = path.stat().st_size
    if size > MAX_RECORD_BYTES or size <= 0:
        raise KnowledgeError("knowledge record exceeds allowed size")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError, OSError) as exc:
        raise KnowledgeError("knowledge record is not valid JSON") from exc


def load_database(*, build: str = PINNED_BUILD, pack_dir: Path | None = None) -> KnowledgeDatabase:
    """Load only a specifically verified build; never auto-fallback to a nearby 1.7."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+) rev(\d+)", build) if isinstance(build, str) else None
    if match is None:
        raise KnowledgeError("requested build must be exact major.minor.patch revrevision")
    if pack_dir is None and build not in BUNDLED_PACKS:
        raise KnowledgeError("no bundled knowledge pack for requested exact build")
    directory = (DATABASE_ROOT / BUNDLED_PACKS[build]) if pack_dir is None else Path(pack_dir)
    if directory.is_symlink() or not directory.is_dir():
        raise KnowledgeError("knowledge directory missing or linked")
    manifest = _read_json(directory / "manifest.json")
    if not isinstance(manifest, dict) or set(manifest) != {
        "schemaVersion", "gameBuild", "gameVersion", "coverage", "source", "collections"
    }:
        raise KnowledgeError("unsupported manifest schema")
    if (type(manifest["schemaVersion"]) is not int or manifest["schemaVersion"] != 1
            or manifest["gameBuild"] != build
            or manifest["gameVersion"] != match.group(1) + "." + match.group(2)
            or manifest["coverage"] != "partial"
            or not isinstance(manifest["source"], str) or not manifest["source"].strip()):
        raise KnowledgeError("manifest build or coverage is not independently verified")
    files = manifest["collections"]
    if not isinstance(files, dict) or set(files) != set(COLLECTIONS.values()):
        raise KnowledgeError("manifest collection list is incomplete")
    seen = set()
    result = {}
    for kind, collection_name in COLLECTIONS.items():
        filename = files[collection_name]
        if (not isinstance(filename, str) or not re.fullmatch(r"[a-z-]+\.json", filename)
                or filename in seen):
            raise KnowledgeError("invalid or duplicate knowledge filename")
        seen.add(filename)
        rows = _read_json(directory / filename)
        if not isinstance(rows, list) or len(rows) > 20_000:
            raise KnowledgeError("invalid knowledge collection")
        by_symbol = {}
        for row in rows:
            if (not isinstance(row, dict)
                    or not {"symbol", "source"} <= set(row)
                    or not set(row) <= {"symbol", "source", "parameters"}
                    or not isinstance(row["symbol"], str) or not SYMBOL.fullmatch(row["symbol"])
                    or not isinstance(row["source"], str) or not row["source"].strip()
                    or len(row["source"]) > 300 or row["symbol"] in by_symbol):
                raise KnowledgeError("invalid or duplicate knowledge symbol")
            if "parameters" in row:
                parameters = row["parameters"]
                if (kind not in {"method", "harmony"}
                        or not isinstance(parameters, list) or len(parameters) > 24
                        or any(not isinstance(p, str) or
                               not re.fullmatch(r"[\x21-\x7e]{1,200}", p) for p in parameters)):
                    raise KnowledgeError("invalid method argument types")
            by_symbol[row["symbol"]] = row
        result[kind] = by_symbol
    return KnowledgeDatabase(manifest, result)


def _static_issue(issues: list, code: str, *, definite: bool = True):
    # Deliberately omit private paths, raw XML, package descriptions and symbols.
    # Codes are the only publicly safe diagnostic interface by default.
    issues.append({"code": code, "certainty": "definite" if definite else "unknown"})


def _parse_xml_file(path: Path):
    if path.is_symlink() or not path.is_file():
        raise KnowledgeError("missing or linked XML")
    # A capped read, not an unchecked read_bytes() after a racy stat check.
    with path.open("rb") as stream:
        data = stream.read(MAX_XML_BYTES + 1)
    if len(data) > MAX_XML_BYTES:
        raise KnowledgeError("oversized XML")
    return mod_load_plan.parse_xml(data)


def inspect_mod(mod: Path, db: KnowledgeDatabase, *,
                active_packages=(), complete_set: bool = False) -> dict:
    """Static-only read of a local MOD. Definite vs incomplete issues are separate."""
    # mod_load_plan is qualified only for this exact build. Knowledge packs
    # for newer builds can support name queries, but their loader rules have
    # NOT been verified. Never silently scan them with the old 1.7 policy.
    if db.metadata["gameBuild"] != PINNED_BUILD:
        raise KnowledgeError("no verified MOD loader policy for requested game build")
    root = Path(mod).absolute()
    issues, local_defs = [], []
    stats = {"filesConsidered": 0, "xmlFilesChecked": 0, "definitionsFound": 0}
    pack_id = None
    files = []
    try:
        if not root.is_dir() or root.is_symlink() or any(p.is_symlink() for p in root.parents):
            raise KnowledgeError("MOD folder is unavailable or linked")
        # Count bytes we will actually READ, not opaque texture/audio/AssetBundle
        # payloads. A legitimate large MOD should not fail metadata-only checks.
        metadata_bytes = 0
        visited = 0
        for path in root.rglob("*"):
            visited += 1
            if visited > 2 * MAX_FILES:
                raise KnowledgeError("too many directory entries")
            if path.is_symlink():
                _static_issue(issues, "unsafeFile")
                continue
            if not path.is_file():
                continue
            if len(files) >= MAX_FILES:
                raise KnowledgeError("too many files")
            rel = path.relative_to(root).as_posix()
            if not rel or "\\" in rel or any(p in (".", "..", "") for p in rel.split("/")):
                raise KnowledgeError("unsafe relative path")
            files.append((rel, path))
            if rel in ("About/About.xml", "LoadFolders.xml"):
                metadata_bytes += path.stat().st_size
                if metadata_bytes > MAX_INPUT_BYTES:
                    raise KnowledgeError("metadata exceeds bounded read budget")
        files.sort(key=lambda item: item[0])
        stats["filesConsidered"] = len(files)
        names = {p for p, _ in files}
        if "About/About.xml" not in names:
            _static_issue(issues, "missingAbout")
        else:
            try:
                meta = _parse_xml_file(root / "About" / "About.xml")
                if meta.tag != "ModMetaData":
                    raise KnowledgeError("invalid metadata root")
                pack_id = (meta.findtext("packageId") or "").strip()
                if not PACKAGE_ID.fullmatch(pack_id):
                    _static_issue(issues, "invalidPackageId")
                versions = [(n.text or "").strip() for n in meta.findall("./supportedVersions/li")]
                if versions and db.metadata["gameVersion"] not in versions:
                    _static_issue(issues, "versionMismatch")
                if not versions:
                    _static_issue(issues, "versionNotDeclared", definite=False)

                active = set()
                for item in active_packages:
                    if not isinstance(item, str) or not PACKAGE_ID.fullmatch(item):
                        raise KnowledgeError("invalid active package identifier")
                    active.add(item.casefold())
                if pack_id and PACKAGE_ID.fullmatch(pack_id):
                    active.add(pack_id.casefold())
                try:
                    for dep in mod_load_plan.missing_dependencies(meta, active):
                        _static_issue(issues, "dependencyMissing" if complete_set else "dependencyNotChecked",
                                      definite=bool(complete_set))
                except mod_load_plan.LoadPlanError:
                    _static_issue(issues, "invalidDependencies")
                for node in meta.findall("./incompatibleWith/li"):
                    if (node.text or "").strip().casefold() in active:
                        _static_issue(issues, "incompatibleMod")

                config = (root / "LoadFolders.xml")
                if config.is_symlink():
                    raise KnowledgeError("linked load-folder metadata")
                load_data = None
                if config.is_file():
                    with config.open("rb") as stream:
                        load_data = stream.read(MAX_XML_BYTES + 1)
                    if len(load_data) > MAX_XML_BYTES:
                        raise KnowledgeError("oversized load-folder metadata")
                if load_data is not None and not complete_set:
                    # Conditional paths cannot be resolved from the target
                    # package alone. A partial active MOD list must not make
                    # unexamined XML look clean.
                    load_xml = mod_load_plan.parse_xml(load_data)
                    conditional_keys = {"IfModActive", "IfModActiveAll", "IfModNotActive"}
                    if any(conditional_keys.intersection(item.attrib)
                           for item in load_xml.iter("li")):
                        _static_issue(issues, "conditionalLoadFoldersNotChecked",
                                      definite=False)
                folders = mod_load_plan.load_folders(names, load_data, active)
            except mod_load_plan.LoadPlanError as exc:
                # A parser refusing to model a loader condition or version
                # cannot prove the MOD invalid. Preserve unknown rather than
                # producing a false incompatibility verdict.
                if exc.code.startswith("unsupported"):
                    _static_issue(issues, "unsupportedLoaderMetadata", definite=False)
                else:
                    _static_issue(issues, "invalidMetadata")
                folders = []
            except (OSError, ValueError, KnowledgeError):
                _static_issue(issues, "invalidMetadata")
                folders = []

            inspected_bytes = 0
            declared = set()
            unconditional_defs = set()
            conditional_seen = False
            for rel, path in files:
                if not rel.casefold().endswith(".xml"):
                    continue
                if not mod_load_plan.select_asset(rel, folders, "English"):
                    continue
                # Only actual Defs / Patches documents; no auto-run of arbitrary XML.
                lower = rel.casefold().split("/")
                if not any(p in ("defs", "patches") for p in lower[:-1]):
                    continue
                inspected_bytes += path.stat().st_size
                if inspected_bytes > MAX_SCAN_XML_BYTES or metadata_bytes + inspected_bytes > MAX_INPUT_BYTES:
                    _static_issue(issues, "xmlInputLimit")
                    break
                try:
                    node = _parse_xml_file(path)
                    stats["xmlFilesChecked"] += 1
                except (OSError, ValueError, mod_load_plan.LoadPlanError):
                    _static_issue(issues, "invalidXml")
                    continue
                if node.tag != "Defs":
                    continue
                for entry in node:
                    name = (entry.findtext("defName") or "").strip()
                    # Only a full declaration; inherited/abstract child nodes
                    # without defName are not treated as missing definitions.
                    if name and entry.tag.endswith("Def") and SYMBOL.fullmatch(name):
                        key = (entry.tag, name)
                        conditional = any(attr.startswith("MayRequire") for attr in entry.attrib)
                        if conditional and not conditional_seen:
                            _static_issue(issues, "conditionalDefNotChecked",
                                          definite=False)
                            conditional_seen = True
                        if key in declared:
                            if conditional or key not in unconditional_defs:
                                _static_issue(issues, "conditionalDefDuplicateNotChecked",
                                              definite=False)
                            else:
                                _static_issue(issues, "duplicateLocalDef")
                        else:
                            declared.add(key)
                            local_defs.append({"type": entry.tag, "defName": name})
                        if not conditional:
                            unconditional_defs.add(key)
    except (OSError, ValueError, KnowledgeError):
        _static_issue(issues, "unsafeInput")

    stats["definitionsFound"] = len(local_defs)
    has_definite = any(i["certainty"] == "definite" for i in issues)
    status = ("staticIssuesFound" if has_definite else
              "staticIncomplete" if issues else "staticChecksPassed")
    return {
        "recordType": "modKnowledgePreflight",
        "schemaVersion": 1,
        "status": status,
        "gameBuild": db.metadata["gameBuild"],
        "catalogCoverage": db.metadata["coverage"],
        "gameVerification": "notRun",
        "runtimeQualified": False,
        "packageId": pack_id if pack_id and PACKAGE_ID.fullmatch(pack_id) else None,
        "issues": issues,
        "statistics": stats,
        "localDefinitions": sorted(local_defs, key=lambda d: (d["type"], d["defName"])),
        "notChecked": ["realGameLoading", "harmonyApplication", "crossModDefResolution",
                       "xmlPatchApplication", "nativeBehavior", "gameplay", "privateModIndex"],
    }



def check_requirements(path: Path, db: KnowledgeDatabase) -> dict:
    """Batch positive-evidence queries; unknown symbols never become missing errors."""
    requested = Path(path)
    if requested.is_symlink() or not requested.is_file() or requested.stat().st_size > 256 * 1024:
        raise KnowledgeError("invalid requirements input")
    data = _read_json(requested)
    if (not isinstance(data, dict) or set(data) != {"schemaVersion", "gameBuild", "requires"}
            or type(data["schemaVersion"]) is not int or data["schemaVersion"] != 1
            or data["gameBuild"] != db.metadata["gameBuild"]
            or not isinstance(data["requires"], list) or len(data["requires"]) > 1000):
        raise KnowledgeError("invalid requirements schema/build")
    seen, results = set(), []
    for row in data["requires"]:
        if (not isinstance(row, dict)
                or not {"kind", "symbol"} <= set(row)
                or not set(row) <= {"kind", "symbol", "parameters"}):
            raise KnowledgeError("invalid symbol requirement")
        kind, symbol = row["kind"], row["symbol"]
        if (not isinstance(kind, str) or not isinstance(symbol, str)
                or kind not in COLLECTIONS or not SYMBOL.fullmatch(symbol)
                or (kind, symbol) in seen):
            raise KnowledgeError("invalid or repeated requirement")
        seen.add((kind, symbol))
        results.append(db.query(kind, symbol, parameters=row.get("parameters")))
    known = sum(row["status"] == "present" for row in results)
    unknown = len(results) - known
    return {
        "recordType": "offlineKnowledgeRequirements",
        "schemaVersion": 1,
        "gameBuild": db.metadata["gameBuild"],
        "status": "staticIncomplete" if unknown or not results else "staticChecksPassed",
        "counts": {"present": known, "unknown": unknown},
        "results": results,
        "gameVerification": "notRun",
        "runtimeQualified": False,
        "notChecked": ["runtimeResolution", "overloadSignature", "nativeBehavior", "modConflicts"],
    }

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    query = commands.add_parser("query", help="query a verified known symbol, or return unknown")
    scan = commands.add_parser("scan", help="scan a local MOD without R2, game or Worker")
    verify = commands.add_parser("validate-db", help="validate pack schema and show safe counts")
    batch = commands.add_parser("check", help="batch-check explicit API/Def requirements offline")
    for cmd in (query, scan, verify, batch):
        cmd.add_argument("--build", default=PINNED_BUILD)
        cmd.add_argument("--pack-dir", type=Path, default=None)
    batch.add_argument("--requirements", type=Path, required=True)
    query.add_argument("--kind", choices=tuple(COLLECTIONS), required=True)
    query.add_argument("--symbol", required=True)
    scan.add_argument("--mod", type=Path, required=True)
    scan.add_argument("--active", action="append", default=[])
    scan.add_argument("--complete-set", action="store_true")
    args = parser.parse_args(argv)
    try:
        db = load_database(build=args.build, pack_dir=args.pack_dir)
        if args.command == "query":
            result = db.query(args.kind, args.symbol)
            code = 0 if result["status"] == "present" else 3
        elif args.command == "scan":
            result = inspect_mod(args.mod, db,
                                 active_packages=args.active, complete_set=args.complete_set)
            code = {"staticChecksPassed": 0, "staticIssuesFound": 1, "staticIncomplete": 3}[result["status"]]
        elif args.command == "check":
            result = check_requirements(args.requirements, db)
            code = 0 if result["status"] == "staticChecksPassed" else 3
        else:
            result = {
                "recordType": "offlineKnowledgePackStatus", "status": "valid",
                "gameBuild": db.metadata["gameBuild"],
                "coverage": db.metadata["coverage"],
                "counts": {kind: len(items) for kind, items in db.collections.items()},
                "gameVerification": "notRun",
            }
            code = 0
    except (KnowledgeError, OSError, ValueError):
        print(json.dumps({"status": "blocked", "code": "knowledgeUnavailable"}, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
