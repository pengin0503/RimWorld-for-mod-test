"""Read-only readiness gate for the Linux RimWorld build now in R2 Game-Linux/.

Never accepts a new adapter or grants qualification. This audit only checks
the fixed set of private R2 object metadata and a small Version.txt payload.
Any build of a supported family (1.7.x, tools/game_builds.py) can be ready for
the automatic qualification (experiments/official-comparison/qualify_build.py);
``--target 1.7.<build>`` additionally requires that exact build.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import tempfile

try:
    from tools import r2_assets, game_builds
except ImportError:
    import r2_assets
    import game_builds

TARGET = re.compile(r"[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,7}\Z")


def inspect(r2, scratch: Path, target: str | None = None):
    if target is not None and (not isinstance(target, str) or not TARGET.fullmatch(target)
                               or game_builds.family(target + " rev0") is None):
        raise ValueError("unsupported readiness target")
    listed = {}
    for key in sorted(r2_assets.STATIC_AUDIT_KEYS):
        entries = r2.list_static_audit_key(key)
        if (not isinstance(entries, list) or len(entries) != 1
                or not isinstance(entries[0], dict) or entries[0].get("key") != key
                or type(entries[0].get("size")) is not int
                or entries[0]["size"] < 0):
            continue
        listed[key] = entries[0]["size"]

    result = {"targetBuild": target, "state": "missingIdentityFiles",
              "listedIdentityKeys": len(listed),
              "requiredIdentityKeys": len(r2_assets.STATIC_AUDIT_KEYS),
              "qualified": False}
    key = "Game-Linux/Version.txt"
    if key not in listed:
        return result
    if listed[key] > 256 or listed[key] == 0:
        result["state"] = "invalidVersion"
        return result
    dest = Path(scratch) / "Version.txt"
    if not dest.parent.is_dir() or dest.is_symlink():
        raise ValueError("unsafe private scratch directory")
    # R2.get enforces the object size; refresh avoids a stale cached Version.
    r2.get(key, dest, listed[key], refresh=True)
    try:
        raw = dest.read_bytes()
        if len(raw) > 256:
            return {**result, "state": "invalidVersion"}
        version = raw.decode("ascii").strip()
    except (UnicodeError, OSError):
        return {**result, "state": "invalidVersion"}
    if raw.count(b"\n") > 1 or game_builds.parse_version(version) is None:
        return {**result, "state": "invalidVersion"}
    build = game_builds.build_id(version)
    # A reviewed record is only a folder name here: whether its hashes match is decided at validation time.
    result.update({"version": version, "buildId": build,
                   "reviewedRecord": (game_builds.DATA_ROOT / build / game_builds.RECORD_NAME).is_file()})
    if game_builds.family(version) is None:
        result["state"] = "unsupportedFamily"
    elif target is not None and not version.startswith(target + " "):
        result["state"] = "differentBuild"
    elif len(listed) == len(r2_assets.STATIC_AUDIT_KEYS):
        result["state"] = "readyForAudit"
    return result


def main(argv=None):
    from tools import r2_assets
    args = list(sys.argv[1:] if argv is None else argv)
    target = None
    if args[:1] == ["--target"] and len(args) == 2:
        target = args[1]
    elif args:
        print("usage: python -m tools.build_readiness [--target 1.7.<build>]", file=sys.stderr)
        return 2
    try:
        with tempfile.TemporaryDirectory(prefix="rwmt-build-readiness-") as root:
            with r2_assets.R2(endpoint=os.environ.get("R2_ENDPOINT", ""),
                              bucket="rimworld-17",
                              transport=os.environ.get("RWMT_R2_TRANSPORT", "sdk")) as r2:
                output = inspect(r2, Path(root), target)
    except (OSError, ValueError, r2_assets.AssetError):
        output = {"targetBuild": target, "state": "blocked",
                  "qualified": False, "listedIdentityKeys": 0,
                  "requiredIdentityKeys": len(r2_assets.STATIC_AUDIT_KEYS)}
    print(json.dumps(output, sort_keys=True))
    # Even readyForAudit is not qualified; 0 means the read-only
    # eligibility check completed, not that the build is qualified.
    return 0 if output["state"] == "readyForAudit" else 2


if __name__ == "__main__":
    raise SystemExit(main())
