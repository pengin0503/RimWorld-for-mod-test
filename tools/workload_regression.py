"""Fixed private Linux workload profiles and publication-safe measurements.

No third-party MOD bytes or private index records are included in public summaries.
This module never initiates R2 access; private callers select fixed profiles.
"""
from __future__ import annotations

import math
from statistics import median

PROFILES = {
    "S": ("Vanilla Psycasts Expanded",),
    "M": ("Vanilla Psycasts Expanded", "TD Enhancement Pack"),
}
UNCACHED = tuple("uncached-" + str(i) for i in range(1, 6))
CACHED = tuple("cached-" + str(i) for i in range(1, 6))
EXPECTED = (*UNCACHED, "cache-fill", *CACHED)


PREPARATION_SECONDS = (
    "modFetchSeconds", "gameRuntimeFetchSeconds",
    "snapshotTotalSeconds", "totalInitialSeconds")
PREPARATION_COUNTS = (
    "selectedModCount", "selectedModFiles", "selectedModBytes", "gameFiles")


def summarize_preparation(raw) -> dict:
    """Publish only bounded first-acquisition measurements, never R2 metadata."""
    blocked = {"complete": False, **{key: None for key in
               (*PREPARATION_SECONDS, *PREPARATION_COUNTS)}}
    if not isinstance(raw, dict):
        return blocked
    values = {}
    for key in PREPARATION_SECONDS:
        value = raw.get(key)
        if (type(value) not in (float, int) or not math.isfinite(value)
                or value < 0 or value > 7200):
            return blocked
        values[key] = round(value, 5)
    maximums = {
        "selectedModCount": 20,
        "selectedModFiles": 5000,
        "selectedModBytes": 256 * 1024 * 1024,
        "gameFiles": 1000000,
    }
    for key in PREPARATION_COUNTS:
        value = raw.get(key)
        if type(value) is not int or not 1 <= value <= maximums[key]:
            return blocked
        values[key] = value
    # These are sequential, non-overlapping stages; tolerances cover bounded
    # rounding error without allowing impossible fast end-to-end numbers.
    if values["totalInitialSeconds"] + 0.05 < sum(values[key] for key in
            ("modFetchSeconds", "gameRuntimeFetchSeconds", "snapshotTotalSeconds")):
        return blocked
    return {"complete": True, **values}


def profile_roots(name: str) -> tuple[str, ...]:
    if not isinstance(name, str) or name not in PROFILES:
        raise ValueError("unknown workload profile")
    return PROFILES[name]


def explicit_root_ids(resolved) -> frozenset[str]:
    """Return exact private-index package IDs with duplicate roots rejected."""
    ids = []
    for _, package_id in resolved:
        if not isinstance(package_id, str) or not package_id.strip():
            raise ValueError("invalid explicitly requested package ID")
        ids.append(package_id.casefold())
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError("duplicate or empty explicit workload roots")
    return frozenset(ids)


def loader_order_matches(observed, wanted) -> bool:
    if not isinstance(observed, dict) or observed.get("matches") is not True:
        return False
    actual = observed.get("actual")
    if not isinstance(actual, list) or not all(isinstance(i, str) for i in actual):
        return False
    if not isinstance(wanted, list) or not all(isinstance(i, str) for i in wanted):
        return False
    relevant = [s.casefold() for s in actual if not s.casefold().startswith("ludeon.")]
    expected = [s.casefold() for s in wanted]
    return bool(expected) and relevant == expected and len(expected) == len(set(expected))


def _valid_row(row, case):
    if not isinstance(row, dict) or row.get("case") != case:
        return False
    mode = "cache-fill" if case == "cache-fill" else "cached" if case.startswith("cached-") else "uncached"
    elapsed = row.get("elapsedSeconds")
    rss = row.get("peakRssBytes")
    return (row.get("mode") == mode and row.get("status") == "passed"
            and row.get("orderMatches") is True and type(elapsed) in (int, float)
            and math.isfinite(elapsed) and 0 < elapsed <= 3600
            and type(rss) is int and 0 <= rss <= 1 << 48
            and row.get("baselineCached") is (mode == "cached"))


def valid_measurement_row(row, case):
    """An invalid sample cannot contribute to a complete fixed suite."""
    return case in EXPECTED and _valid_row(row, case)


def summarize_runs(rows) -> dict:
    """Only complete, successful, exact-case samples yield performance statistics."""
    blocked = {"complete": False, "samples": {"uncached": 0, "cached": 0},
               "medianUncachedSeconds": None, "medianCachedSeconds": None,
               "maxPeakRssBytes": None, "speedupPercent": None, "warmOsCache": True}
    if not isinstance(rows, list) or len(rows) != len(EXPECTED):
        return blocked
    by_case = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("case") not in EXPECTED or row["case"] in by_case:
            return blocked
        by_case[row["case"]] = row
    if set(by_case) != set(EXPECTED) or not all(valid_measurement_row(by_case[c], c) for c in EXPECTED):
        return blocked
    uncached = median(by_case[c]["elapsedSeconds"] for c in UNCACHED)
    cached = median(by_case[c]["elapsedSeconds"] for c in CACHED)
    return {"complete": True, "samples": {"uncached": 5, "cached": 5},
            "medianUncachedSeconds": round(uncached, 5),
            "medianCachedSeconds": round(cached, 5),
            "maxPeakRssBytes": max(by_case[c]["peakRssBytes"] for c in EXPECTED),
            "speedupPercent": round((uncached - cached) / uncached * 100, 3),
            "warmOsCache": True}
