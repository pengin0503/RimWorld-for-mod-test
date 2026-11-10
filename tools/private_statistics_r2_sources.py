#!/usr/bin/env python3
"""Read-only private R2 source fetcher for a pinned, isolated Rimworld-Statistics acceptance.

Never print R2 object keys, original names, Mod IDs, paths, credentials, or checksums.
The 49 files reside only inside an ephemeral private runner directory.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from botocore.session import get_session

PREFIX = "Saves/"
BUCKET = "rimworld-17"
EXPECTED_COUNT = 49
EXPECTED_BYTES = 824_593_049
MAX_FILES = 100
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024


def run(destination: Path) -> None:
    access = os.environ["AWS_ACCESS_KEY_ID"]
    secret = os.environ["AWS_SECRET_ACCESS_KEY"]
    endpoint = os.environ["R2_ENDPOINT"]
    if not access or not secret or not endpoint.startswith("https://"):
        raise ValueError("unavailable private R2 credentials")
    client = get_session().create_client(
        "s3", region_name="auto", endpoint_url=endpoint,
        aws_access_key_id=access, aws_secret_access_key=secret,
    )
    entries = []
    token = None
    while True:
        request = {"Bucket": BUCKET, "Prefix": PREFIX, "MaxKeys": 1000}
        if token:
            request["ContinuationToken"] = token
        page = client.list_objects_v2(**request)
        entries.extend(o for o in page.get("Contents", ())
            if o["Key"].lower().endswith((".rws", ".rws.old")))
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
        if response.get("ETag") and obj.get("ETag") and response["ETag"] != obj["ETag"]:
            response["Body"].close()
            raise ValueError("R2 input changed between list and fetch")
        read_bytes = 0
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, "wb") as output, response["Body"] as stream:
                while chunk := stream.read(1024 * 1024):
                    read_bytes += len(chunk)
                    if read_bytes > obj["Size"]:
                        raise ValueError("R2 object exceeded its declared size")
                    output.write(chunk)
            if read_bytes != obj["Size"]:
                raise ValueError("R2 object download is incomplete")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)

    # Aggregate count only. Never disclose original per-file length or key.
    print("private_source_ready,files,bytes")
    print(f"verified,{len(entries)},{size}")


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
