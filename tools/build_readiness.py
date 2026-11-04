"""Read-only readiness gate for a candidate Linux RimWorld build.

Never accepts a new adapter or grants qualification. This audit only checks
the fixed set of private R2 object metadata and a small Version.txt payload.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile

try:
    from tools import r2_assets
except ImportError:
    import r2_assets

SUPPORTED_TARGET = "1.7.4995"
VERSION = re.compile(r"1\.7\.([0-9]{4,6}) rev([0-9]{1,9})\Z")


def inspect(r2, scratch: Path, target: str = SUPPORTED_TARGET):
    if target != SUPPORTED_TARGET:
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
    if raw.count(b"\n") > 1 or not VERSION.fullmatch(version):
        return {**result, "state": "invalidVersion"}
    if not version.startswith(target + " "):
        result["state"] = "differentBuild"
    elif len(listed) == len(r2_assets.STATIC_AUDIT_KEYS):
        result["state"] = "readyForAudit"
    return result


def main():
    from tools import r2_assets
    try:
        with tempfile.TemporaryDirectory(prefix="rwmt-build-readiness-") as root:
            with r2_assets.R2(endpoint=os.environ.get("R2_ENDPOINT", ""),
                              bucket="rimworld-17",
                              transport=os.environ.get("RWMT_R2_TRANSPORT", "sdk")) as r2:
                output = inspect(r2, Path(root))
    except (OSError, ValueError, r2_assets.AssetError):
        output = {"targetBuild": SUPPORTED_TARGET, "state": "blocked",
                  "qualified": False, "listedIdentityKeys": 0,
                  "requiredIdentityKeys": len(r2_assets.STATIC_AUDIT_KEYS)}
    print(json.dumps(output, sort_keys=True))
    # Even readyForAudit is not qualified; 0 means the read-only
    # eligibility check completed, not that 1.7.4995 is supported.
    return 0 if output["state"] == "readyForAudit" else 2


if __name__ == "__main__":
    raise SystemExit(main())
