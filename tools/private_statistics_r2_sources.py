#!/usr/bin/env python3
"""Read-only private R2 source fetcher for a pinned, isolated Rimworld-Statistics acceptance.

Never print R2 object keys, original names, Mod IDs, paths, credentials, or checksums.
The 49 files reside only inside an ephemeral private runner directory.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

from botocore.config import Config
from botocore.session import Session

PREFIX = "Saves/"
BUCKET = "rimworld-17"
EXPECTED_COUNT = 49
EXPECTED_BYTES = 824_593_049
MAX_FILES = 100
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024


def _validate_endpoint(endpoint: str) -> None:
    parsed = urlsplit(endpoint)
    host = parsed.hostname or ""
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment
            or not re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)?\.r2\.cloudflarestorage\.com", host)):
        raise ValueError("unavailable private R2 credentials")


def run(destination: Path) -> None:
    access = os.environ["AWS_ACCESS_KEY_ID"]
    secret = os.environ["AWS_SECRET_ACCESS_KEY"]
    endpoint = os.environ["R2_ENDPOINT"]
    if not access or not secret:
        raise ValueError("unavailable private R2 credentials")
    _validate_endpoint(endpoint)
    session = Session(session_vars={
        "profile": (None, None, None, None),
        "config_file": (None, None, os.devnull, None),
        "credentials_file": (None, None, os.devnull, None),
    })
    client = session.create_client(
        "s3", region_name="auto", endpoint_url=endpoint,
        aws_access_key_id=access, aws_secret_access_key=secret,
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=10,
            read_timeout=60,
            retries={"mode": "standard", "total_max_attempts": 3},
        ),
    )
    try:
        entries = []
        token = None
        while True:
            request = {"Bucket": BUCKET, "Prefix": PREFIX, "MaxKeys": 1000}
            if token:
                request["ContinuationToken"] = token
            page = client.list_objects_v2(**request)
            entries.extend(o for o in page.get("Contents", ())
                if o["Key"].lower().endswith((".rws", ".rws.old")))
            if len(entries) > MAX_FILES:
                raise ValueError("the pinned R2 original-save inventory changed")
            if not page.get("IsTruncated"):
                break
            token = page["NextContinuationToken"]

        # Any unexpected inventory change blocks the run, rather than selecting a
        # different private dataset and comparing an old performance baseline.
        size = sum(o["Size"] for o in entries)
        if len(entries) != EXPECTED_COUNT or size != EXPECTED_BYTES or len(entries) > MAX_FILES or size > MAX_TOTAL_BYTES:
            raise ValueError("the pinned R2 original-save inventory changed")

        destination.mkdir(mode=0o700, parents=False, exist_ok=False)
        for index, obj in enumerate(sorted(entries, key=lambda x: x["Key"])):
            suffix = ".rws.old" if obj["Key"].lower().endswith(".rws.old") else ".rws"
            temporary = destination / ("source-" + str(index).zfill(3) + suffix + ".part")
            target = destination / ("source-" + str(index).zfill(3) + suffix)
            # Private original names only live transiently in this process's memory.
            response = client.get_object(Bucket=BUCKET, Key=obj["Key"])
            body = response["Body"]
            try:
                if response.get("ETag") and obj.get("ETag") and response["ETag"] != obj["ETag"]:
                    raise ValueError("R2 input changed between list and fetch")
                read_bytes = 0
                fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                try:
                    with os.fdopen(fd, "wb") as output:
                        while chunk := body.read(1024 * 1024):
                            read_bytes += len(chunk)
                            if read_bytes > obj["Size"]:
                                raise ValueError("R2 object exceeded its declared size")
                            output.write(chunk)
                    if read_bytes != obj["Size"]:
                        raise ValueError("R2 object download is incomplete")
                    temporary.replace(target)
                finally:
                    temporary.unlink(missing_ok=True)
            finally:
                body.close()

        # Aggregate count only. Never disclose original per-file length or key.
        print("private_source_ready,files,bytes")
        print(f"verified,{len(entries)},{size}")
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.private_dir)
        return 0
    except Exception:
        # Botocore and OSError error strings can contain R2 keys, access IDs
        # or private paths. No raw exception/traceback may enter public logs.
        print("Private R2 source preparation failed; check secure runner diagnostics.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
