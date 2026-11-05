"""P4: bounded private workload regression. Never publish real game/MOD assets."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
import time
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from tools import codex_workflow as cw, validation_host as vh, workload_regression as wr, cow_benchmark as cow

MAX_BYTES = 256 * 1024 * 1024
MAX_FILES = 5000
MAX_MODS = 20


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=("prepare", "run", "publish", "cow"))
    p.add_argument("--profile", required=True, choices=tuple(wr.PROFILES))
    p.add_argument("--private-root", required=True)
    p.add_argument("--worker", default="worker/bin")
    return p


def write_private(path: Path, payload):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, allow_nan=False), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)


def read_private(path):
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("missing or oversized private workload state")
    return json.loads(path.read_text(encoding="utf-8"))


def check_request_digest(manifest: dict, request_path: Path):
    expected = manifest.get("requestSha256")
    if (not isinstance(expected, str) or len(expected) != 64
            or any(char not in "0123456789abcdef" for char in expected)):
        raise ValueError("private request manifest has no valid SHA-256")
    if not request_path.is_file() or request_path.stat().st_size > 1024 * 1024:
        raise ValueError("private request missing or oversized")
    if sha256(request_path.read_bytes()).hexdigest() != expected:
        raise ValueError("private request changed since preparation")


def prepare_profile(root: Path, profile: str):
    roots = wr.profile_roots(profile)
    root = cw._safe_private(root)
    if (root / "profile.json").exists() or (root / "request.json").exists():
        raise ValueError("private profile already prepared; use a fresh root")
    # The precise Workshop IDs and PackageIds are resolved by fetch_mods
    # against the private index; never guess IDs from display names.
    fetch = cw.fetch_mods(
        SimpleNamespace(private_root=root, refresh=False, aws="aws",
                        index_zip=None, target=roots[-1], local_target=None,
                        dependency=list(roots[:-1]), official=["Core", "Royalty"],
                        language="English", scope="validation"),
        root_targets=roots, max_selected_bytes=MAX_BYTES,
        max_selected_files=MAX_FILES, max_mods=MAX_MODS)
    # All metadata and selected payload was bounded before the game was acquired.
    prepared = cw.prepare(SimpleNamespace(private_root=root, refresh=False, aws="aws"))
    raw_request = (root / "request.json").read_bytes()
    manifest = {"profile": profile, "requestSha256": sha256(raw_request).hexdigest(),
                "runtimePrepared": True}
    write_private(root / "profile.json", manifest)
    return {"profile": profile, "mods": len(fetch["fetched"]),
            "modSelectedBytes": sum(x["r2"]["listedBytes"] for x in fetch["fetched"]),
            "modSelectedFiles": sum(x["r2"]["selected"] for x in fetch["fetched"]),
            "gameFiles": prepared.get("files"), "gameTimings": prepared.get("timings")}


def parse_measurement(case, result, request, elapsed_seconds):
    """Store a fixed-schema row. No raw messages, MOD names or private paths."""
    expected = [mod["packageId"] for mod in request.get("mods", [])]
    processes = result.get("process") if isinstance(result.get("process"), dict) else {}
    peaks = [p.get("peakRssBytes") for p in (processes.get("target"), processes.get("baseline"))
             if isinstance(p, dict)]
    peaks = [p for p in peaks if type(p) is int and 0 <= p <= 1 << 48]
    diagnostics = result.get("diagnostics") if isinstance(result.get("diagnostics"), dict) else {}
    mode = "cache-fill" if case == "cache-fill" else "cached" if case.startswith("cached-") else "uncached"
    return {"case": case, "mode": mode,
            "status": result.get("status") if result.get("status") in ("passed", "failed", "blocked", "incomplete")
            else "incomplete",
            "orderMatches": wr.loader_order_matches(result.get("modOrder"), expected),
            "baselineCached": diagnostics.get("baselineCached") is True,
            "elapsedSeconds": round(elapsed_seconds, 5) if type(elapsed_seconds) in (int, float)
            and math.isfinite(elapsed_seconds) and 0 < elapsed_seconds <= 3600 else None,
            "peakRssBytes": max(peaks) if peaks else None}


def run_profile(root: Path, worker: Path, profile: str):
    wr.profile_roots(profile)
    root = cw._safe_private(root)
    manifest = read_private(root / "profile.json")
    request_path = root / "request.json"
    if manifest.get("profile") != profile or not request_path.is_file() or not (root / "game-snapshot").is_dir():
        raise ValueError("profile is not prepared")
    check_request_digest(manifest, request_path)
    worker = Path(worker).resolve()
    if not worker.exists():
        raise ValueError("Worker has not been built")
    request = read_private(request_path)
    if request.get("levels") != ["A"] or request.get("official") != ["Core", "Royalty"]:
        raise ValueError("workload profile request has an unexpected validation scope")
    if not request.get("mods") or not all(type(m.get("target")) is bool for m in request["mods"]):
        raise ValueError("workload MOD selection is invalid")
    cases = ["uncached-1", "cache-fill", "cached-1"]
    for i in range(2, 6):
        cases.extend(("uncached-" + str(i), "cached-" + str(i)))
    if set(cases) != set(wr.EXPECTED):
        raise AssertionError("internal workload suite registry is invalid")
    runs_dir = root / "workload-runs"
    if runs_dir.exists() or (root / "workload-rows.json").exists():
        raise ValueError("workload outputs already exist; use a new private root")
    runs_dir.mkdir(mode=0o700)
    rows = []
    for case in cases:
        is_cache = case.startswith("cached-") or case == "cache-fill"
        mark = time.monotonic()
        with cw._no_cloud_credentials():
            result = vh.run_validation(
                root / "game-snapshot", request_path, runs_dir / case, worker,
                baseline_cache=root / "workload-baseline-cache" if is_cache else None,
                hash_cache=root / "workload-hash-cache.json" if is_cache else None)
        row = parse_measurement(case, result, request, time.monotonic() - mark)
        rows.append(row)
        # Checkpoint safely: a crash must never masquerade as 11 completed runs.
        write_private(root / "workload-rows.json", rows)
    summary = wr.summarize_runs(rows)
    write_private(root / "workload-summary.json", summary)
    return summary


def run_cow_profile(root: Path, profile: str):
    """Opt-in Btrfs benchmark; never calls R2 or runs the game Worker."""
    wr.profile_roots(profile)
    root = cw._safe_private(root)
    manifest = read_private(root / "profile.json")
    request = root / "request.json"
    if (manifest.get("profile") != profile or not request.is_file()
            or not (root / "mods").is_dir()):
        raise ValueError("private MOD workload is not prepared")
    check_request_digest(manifest, request)
    if (root / "cow-summary.json").exists():
        raise ValueError("cow benchmark already recorded; use a new private root")
    with cw._no_cloud_credentials():
        summary = cow.run_benchmark(root)
    write_private(root / "cow-summary.json", summary)
    return summary


def publish_profile(root: Path, profile: str):
    root = cw._safe_private(root)
    manifest = read_private(root / "profile.json")
    if manifest.get("profile") != profile:
        raise ValueError("profile does not match private manifest")
    check_request_digest(manifest, root / "request.json")
    rows = read_private(root / "workload-rows.json")
    # Always regenerate and whitelist; do not trust a stale summary file.
    return wr.summarize_runs(rows)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.phase == "prepare":
            output = prepare_profile(Path(args.private_root), args.profile)
        elif args.phase == "run":
            output = run_profile(Path(args.private_root), Path(args.worker), args.profile)
        elif args.phase == "cow":
            output = run_cow_profile(Path(args.private_root), args.profile)
        else:
            output = publish_profile(Path(args.private_root), args.profile)
    except (ValueError, OSError, cw.WorkflowError, vh.Blocked) as exc:
        code = getattr(exc, "code", "workloadBlocked")
        print(json.dumps({"complete": False, "code": code}, sort_keys=True), file=sys.stderr)
        return 2
    # Preparation results remain private by default. Public invocation of
    # publish exposes only fixed numeric, boolean and enum fields.
    if args.phase == "prepare":
        print(json.dumps({"profile": args.profile, "prepared": True}, sort_keys=True))
    else:
        print(json.dumps(output, allow_nan=False, sort_keys=True))
    return 0 if args.phase == "prepare" or output["complete"] or (
        args.phase == "cow" and output.get("status") == "unsupportedFilesystem") else 1


if __name__ == "__main__":
    raise SystemExit(main())
