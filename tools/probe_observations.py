"""Experimental, private-only structured checks for finite-tick probe logs.

This does NOT extend bounded-tick.v1 qualification. RWMT-PROBE warnings
are self-reported by a user-supplied probe and are not independently verified
game state. No runtime method calls or arbitrary reflection are performed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

MARKER = "RWMT-PROBE "
OBS_ID = re.compile(r"probe\.[A-Za-z][A-Za-z0-9_.-]{0,127}\Z")
MAX_LINE = 8192
MAX_EVENTS = 20000
MAX_LOG_BYTES = 8 * 1024 * 1024
MAX_PROBES = 256
MAX_EXPECTATIONS = 64


def _integer(value):
    return type(value) is int and -(1 << 63) <= value < (1 << 63)


def _valid_key(tick, identifier):
    return (type(tick) is int and 0 <= tick <= 60000
            and isinstance(identifier, str) and OBS_ID.fullmatch(identifier) is not None)


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON keys")
        result[key] = value
    return result


def _expected(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_EXPECTATIONS:
        raise ValueError("expected 1..64 observation assertions")
    result = {}
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {"tick", "id", "equals"}
                or not _valid_key(row["tick"], row["id"]) or not _integer(row["equals"])):
            raise ValueError("invalid probe expectation")
        key = (row["tick"], row["id"])
        if key in result:
            raise ValueError("duplicate probe expectation")
        result[key] = row["equals"]
    return result


def evaluate_events(lines, expectations) -> dict:
    """Never return passed/qualified: log provenance is not authoritative."""
    expected = _expected(expectations)
    observations = {}
    invalid = False
    total_bytes = 0
    count = 0
    probes = 0
    for line in lines:
        count += 1
        if not isinstance(line, str) or count > MAX_EVENTS:
            invalid = True
            break
        total_bytes += len(line.encode("utf-8", errors="replace"))
        if len(line) > MAX_LINE or total_bytes > MAX_LOG_BYTES:
            invalid = True
            break
        try:
            event = json.loads(line, object_pairs_hook=_unique_keys)
        except (ValueError, TypeError):
            invalid = True
            continue
        if not isinstance(event, dict):
            invalid = True
            continue
        message = event.get("message")
        if not isinstance(message, str) or not message.startswith(MARKER):
            continue
        probes += 1
        if probes > MAX_PROBES or event.get("level") != "warning":
            invalid = True
            continue
        try:
            probe = json.loads(message[len(MARKER):], object_pairs_hook=_unique_keys)
        except (ValueError, TypeError):
            invalid = True
            continue
        if (not isinstance(probe, dict)
                or set(probe) != {"schemaVersion", "tick", "id", "value"}
                or type(probe["schemaVersion"]) is not int or probe["schemaVersion"] != 1
                or not _valid_key(probe["tick"], probe["id"]) or not _integer(probe["value"])):
            invalid = True
            continue
        key = (probe["tick"], probe["id"])
        if key in observations:
            invalid = True
            continue
        observations[key] = probe["value"]

    checks = []
    missing = False
    mismatch = False
    for key, target in expected.items():
        value = observations.get(key)
        absent = key not in observations
        missing |= absent
        mismatch |= not absent and value != target
        checks.append({"tick": key[0], "id": key[1], "expected": target,
                       "actual": None if absent else value,
                       "outcome": "missing" if absent else "match" if value == target else "mismatch"})
    return {"status": "incomplete" if invalid or missing else "mismatch" if mismatch else "matched",
            "fidelity": "experimental", "source": "untrustedProbeLog",
            "checks": checks, "observed": len(observations), "invalidEvidence": invalid}


def _read_bounded(path: Path, limit: int):
    if path.stat().st_size > limit:
        raise ValueError("private input exceeds safe size")
    return path.read_text(encoding="utf-8").splitlines()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--events", type=Path, required=True, help="private Worker events.jsonl")
    p.add_argument("--expectations", type=Path, required=True, help="private JSON array of assertions")
    a = p.parse_args(argv)
    try:
        raw = a.expectations
        if raw.stat().st_size > 64 * 1024:
            raise ValueError("expectations too large")
        checks = json.loads(raw.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys)
        output = evaluate_events(_read_bounded(a.events, MAX_LOG_BYTES), checks)
    except (OSError, UnicodeError, ValueError, TypeError):
        print('{"status":"incomplete","fidelity":"experimental","invalidEvidence":true}')
        return 2
    print(json.dumps(output, sort_keys=True, ensure_ascii=True, allow_nan=False))
    return 0 if output["status"] == "matched" else 1


if __name__ == "__main__":
    raise SystemExit(main())
