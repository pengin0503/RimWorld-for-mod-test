"""Measure private *real selected MOD files* copied versus Btrfs reflinked.

This is a standalone optional benchmark, not a replacement for the
Controller's integrity and snapshot-verification paths. The public output
contains only fixed case/mode counts and aggregate numeric timing fields.
"""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import shutil
from statistics import median
import subprocess
import sys
import tempfile
import time

MAX_FILES = 5000
MAX_BYTES = 256 * 1024 * 1024
REPEATS = 5
MODES = ("copy", "reflink")
CASES = frozenset(f"{mode}-{i}" for mode in MODES for i in range(1, REPEATS + 1))


def manifest(root: Path, *, max_files: int = MAX_FILES, max_bytes: int = MAX_BYTES):
    """Immutable bounded content digest for all regular files, including empty ones."""
    if type(max_files) is not int or max_files < 1 or type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("invalid file budget")
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("invalid MOD directory")
    rows = []
    size = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("unsafe MOD payload")
        if path.is_dir():
            continue
        st = path.stat()
        size += st.st_size
        if size > max_bytes or len(rows) >= max_files:
            raise ValueError("private MOD payload exceeds benchmark budget")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        rows.append((path.relative_to(root).as_posix(), st.st_size, digest.hexdigest()))
    if not rows:
        raise ValueError("empty MOD payload tree")
    return tuple(rows)


def cp_command(source: Path, destination: Path, mode: str):
    """Use GNU cp's forced reflink/no-reflink switches, never shell=True."""
    if mode not in MODES:
        raise ValueError("invalid copy mode")
    return ["cp", "-a", "--reflink=" + ("always" if mode == "reflink" else "never"),
            "--", str(source) + "/.", str(destination)]


def summarize_samples(rows):
    """Reject missing, duplicate, unsafe, or nonintegral observations entirely."""
    empty = {"status": "incomplete", "complete": False,
             "samples": {"copy": 0, "reflink": 0},
             "medianCopySeconds": None, "medianReflinkSeconds": None,
             "reflinkSpeedupPercent": None}
    if not isinstance(rows, list) or len(rows) != 2 * REPEATS:
        return empty
    cases = set()
    values = {mode: [] for mode in MODES}
    for row in rows:
        if not isinstance(row, dict):
            return empty
        case, mode, seconds = row.get("case"), row.get("mode"), row.get("seconds")
        if (case not in CASES or case in cases or mode not in MODES
                or not case.startswith(mode + "-") or row.get("identical") is not True
                or type(seconds) not in (int, float) or not math.isfinite(seconds)
                or seconds <= 0 or seconds > 3600):
            return empty
        cases.add(case)
        values[mode].append(seconds)
    if cases != CASES or any(len(v) != REPEATS for v in values.values()):
        return empty
    copy = median(values["copy"])
    reflink = median(values["reflink"])
    return {"status": "measured", "complete": True,
            "samples": {"copy": REPEATS, "reflink": REPEATS},
            "medianCopySeconds": round(copy, 5),
            "medianReflinkSeconds": round(reflink, 5),
            "reflinkSpeedupPercent": round((copy - reflink) * 100 / copy, 3)}


def filesystem_type(root: Path) -> str:
    if sys.platform != "linux" or shutil.which("cp") is None:
        return "unsupported"
    try:
        p = subprocess.run(["stat", "-f", "-c", "%T", str(root)],
                           capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return "unsupported"
    return p.stdout.strip() if p.returncode == 0 else "unsupported"


def run_benchmark(root: Path, *, btrfs_root: Path | None = None,
                  max_files=MAX_FILES, max_bytes=MAX_BYTES):
    """Benchmark real selected MOD files, with optional Btrfs staging.

    If the private download root is ext4, a dedicated disposable Btrfs mount
    may be supplied. The one-time, integrity-checked stage is *excluded*
    from the ten copy/reflink trial timings and reported separately.
    """
    root = Path(root).resolve()
    original = root / "mods"
    if original.is_symlink() or not original.is_dir():
        raise ValueError("private selected MOD directory missing")
    original_manifest = manifest(original, max_files=max_files, max_bytes=max_bytes)
    mount = root if btrfs_root is None else Path(btrfs_root)
    if mount.is_symlink() or not mount.is_dir():
        raise ValueError("Btrfs scratch root must be an existing real directory")
    mount = mount.resolve()
    if filesystem_type(mount) != "btrfs":
        return {"status": "unsupportedFilesystem", "complete": False,
                "samples": {"copy": 0, "reflink": 0},
                "medianCopySeconds": None, "medianReflinkSeconds": None,
                "reflinkSpeedupPercent": None, "stagingSeconds": None}

    rows = []
    staged_seconds = 0.0
    # This one owned subtree is created/deleted atomically; the selected
    # original MOD payload is NEVER removed or modified.
    with tempfile.TemporaryDirectory(prefix="rwmt-realmod-cow-", dir=mount) as scratch:
        work = Path(scratch)
        source = original
        if original.stat().st_dev != work.stat().st_dev:
            start = time.monotonic()
            source = work / "selected"
            shutil.copytree(original, source)
            staged_seconds = time.monotonic() - start
            if manifest(source, max_files=max_files, max_bytes=max_bytes) != original_manifest:
                return summarize_samples([])
        if work.stat().st_dev != source.stat().st_dev:
            raise ValueError("source and scratch must be on the same Btrfs filesystem")
        for i in range(1, REPEATS + 1):
            modes = MODES if i % 2 else tuple(reversed(MODES))
            for mode in modes:
                destination = work / f"{mode}-{i}"
                destination.mkdir(mode=0o700)
                started = time.monotonic()
                try:
                    cp = subprocess.run(cp_command(source, destination, mode),
                                        capture_output=True, timeout=300, check=False)
                except (OSError, subprocess.SubprocessError):
                    return summarize_samples(rows)
                seconds = time.monotonic() - started
                if cp.returncode != 0:
                    return summarize_samples(rows)
                identical = manifest(destination, max_files=max_files, max_bytes=max_bytes) == original_manifest
                rows.append({"case": f"{mode}-{i}", "mode": mode,
                             "seconds": seconds, "identical": identical})
                shutil.rmtree(destination)
                if not identical:
                    return summarize_samples(rows)
    if manifest(original, max_files=max_files, max_bytes=max_bytes) != original_manifest:
        return summarize_samples([])
    return {**summarize_samples(rows), "stagingSeconds": round(staged_seconds, 5)}
