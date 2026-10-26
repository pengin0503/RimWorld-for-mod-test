"""Fetch explicitly selected private RimWorld assets from Cloudflare R2.

Requires AWS CLI v2 and a bucket-scoped, read-only R2 S3 credential.
This tool never uploads, deletes, executes, or publishes game/mod files.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

MAX_OBJECTS = 5000
MAX_BYTES = 3 * 1024 ** 3
WORKSHOP_ID = re.compile(r"[0-9]{1,20}\Z")


class AssetError(Exception):
    pass


def validate_key(key: str) -> str:
    """Accept only well-formed keys in the approved private game/MOD prefixes."""
    if not key or "\\" in key or any(ord(c) < 32 for c in key):
        raise AssetError("invalid object key")
    parts = key.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise AssetError("object key contains an unsafe path component")
    if parts[0] == "Game-Linux" and len(parts) >= 2:
        return key
    if parts[0] == "Workshop" and len(parts) >= 3 and WORKSHOP_ID.fullmatch(parts[1]):
        return key
    raise AssetError("key must be below Game-Linux/ or Workshop/<numeric ID>/")


def ensure_safe_destination(root: Path, relative: str) -> Path:
    """Reject symlink components to prevent writes escaping the private destination."""
    path = root / PurePosixPath(relative)
    for part in (root, *path.parents):
        if part.is_symlink():
            raise AssetError("destination contains a symbolic link")
    if path.is_symlink():
        raise AssetError("destination file is a symbolic link")
    return path


class R2:
    def __init__(self, *, endpoint: str, bucket: str, aws: str = "aws"):
        parsed = urlsplit(endpoint)
        host = parsed.hostname or ""
        if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or not re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)?\.r2\.cloudflarestorage\.com", host)):
            raise AssetError("R2_ENDPOINT must be a Cloudflare R2 HTTPS S3 endpoint")
        if not bucket or "/" in bucket:
            raise AssetError("invalid R2_BUCKET")
        self.endpoint, self.bucket, self.aws = endpoint, bucket, aws

    def call(self, *args: str) -> dict:
        cmd = [self.aws, "--endpoint-url", self.endpoint, "--region", "auto", "--no-cli-pager", "s3api", *args, "--output", "json"]
        try:
            result = subprocess.run(cmd, text=True, capture_output=True, check=False)
        except FileNotFoundError as exc:
            raise AssetError("AWS CLI not found (install awscli)") from exc
        if result.returncode != 0:
            # Do not echo the complete AWS CLI command or error, which may include private paths.
            raise AssetError(f"R2 operation failed (AWS CLI exit {result.returncode}); check endpoint, permissions and key")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise AssetError("AWS CLI returned invalid JSON") from exc

    def list_prefix(self, prefix: str) -> list[dict]:
        entries = []
        token = None
        while True:
            args = ["list-objects-v2", "--bucket", self.bucket, "--prefix", prefix, "--max-keys", "1000", "--no-paginate"]
            if token:
                args += ["--continuation-token", token]
            page = self.call(*args)
            for item in page.get("Contents", []):
                key = item["Key"]
                if not key.startswith(prefix):
                    raise AssetError("R2 listing escaped requested prefix")
                if key.endswith("/"):
                    continue
                validate_key(key)
                entries.append({"key": key, "size": int(item["Size"])})
                if len(entries) > MAX_OBJECTS:
                    raise AssetError(f"prefix exceeds safety cap of {MAX_OBJECTS} objects")
            token = page.get("NextContinuationToken")
            if not token:
                break
        return entries

    def get(self, key: str, dest: Path, expected_size: int | None, *, refresh: bool = False) -> str:
        validate_key(key)
        ensure_safe_destination(dest.parent, dest.name)
        if dest.exists() and not refresh and (expected_size is None or dest.stat().st_size == expected_size):
            return "cached"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".r2-", dir=dest.parent, delete=False) as temp:
            temporary = Path(temp.name)
        try:
            metadata = self.call("get-object", "--bucket", self.bucket, "--key", key, str(temporary))
            actual = temporary.stat().st_size
            known_size = expected_size if expected_size is not None else metadata.get("ContentLength")
            if known_size is not None and actual != int(known_size):
                raise AssetError("downloaded object has an unexpected length")
            temporary.replace(dest)
        finally:
            temporary.unlink(missing_ok=True)
        return "downloaded"


def selection(scope: str, items: list[dict]) -> list[dict]:
    if scope == "all":
        return items
    selected = []
    for item in items:
        suffix = item["key"].rsplit("/", 1)[-1].lower()
        rel = item["key"].split("/", 2)[-1]
        if scope == "about" and rel.startswith("About/") and suffix.endswith((".xml", ".txt")):
            selected.append(item)
        elif scope == "xml" and suffix.endswith(".xml"):
            selected.append(item)
        elif scope == "xml" and rel.startswith("About/") and suffix.endswith(".txt"):
            selected.append(item)
    return selected


def run(args) -> dict:
    endpoint = args.endpoint or os.environ.get("R2_ENDPOINT", "")
    bucket = args.bucket or os.environ.get("R2_BUCKET", "rimworld-17")
    r2 = R2(endpoint=endpoint, bucket=bucket, aws=args.aws)
    dest = Path(args.dest).expanduser().absolute()
    if args.action == "file":
        key = validate_key(args.key)
        items = [{"key": key, "size": None}]
        prefix = None
    else:
        if args.action == "mod":
            if not WORKSHOP_ID.fullmatch(args.workshop_id):
                raise AssetError("Workshop ID must be numeric")
            prefix = f"Workshop/{args.workshop_id}/"
            scope = args.scope
        else:
            prefix = "Game-Linux/"
            scope = "all" if args.scope == "all" else "xml"
        items = selection(scope, r2.list_prefix(prefix))
        if not items:
            raise AssetError("no matching R2 objects found")
    total = sum(i["size"] or 0 for i in items)
    if len(items) > MAX_OBJECTS or total > MAX_BYTES:
        raise AssetError("selection exceeds object/byte safety cap; narrow the scope")
    summary = {"action": args.action, "scope": getattr(args, "scope", "exact"), "count": len(items),
               "bytesListed": total if prefix else None, "dryRun": args.dry_run,
               "downloaded": 0, "cached": 0}
    if args.dry_run:
        return summary
    for item in items:
        relative = item["key"][len(prefix):] if prefix else item["key"]
        path = ensure_safe_destination(dest, relative)
        outcome = r2.get(item["key"], path, item["size"], refresh=args.refresh)
        summary[outcome] += 1
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", help="Cloudflare R2 endpoint; otherwise R2_ENDPOINT env")
    parser.add_argument("--bucket", help="R2 bucket; otherwise R2_BUCKET env (default rimworld-17)")
    parser.add_argument("--aws", default="aws", help="AWS CLI executable")
    sub = parser.add_subparsers(dest="action", required=True)
    for command in ("file", "mod", "game"):
        p = sub.add_parser(command)
        p.add_argument("--dest", required=True, help="private output directory")
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--refresh", action="store_true", help="replace cached files")
        if command == "file":
            p.add_argument("--key", required=True, help="exact approved R2 object key")
        elif command == "mod":
            p.add_argument("--workshop-id", required=True)
            p.add_argument("--scope", choices=("about", "xml", "all"), default="about")
        else:
            p.add_argument("--scope", choices=("xml", "all"), default="xml")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args), sort_keys=True))
    except AssetError as exc:
        print(f"r2-assets: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
