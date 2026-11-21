"""Shared pieces for the synthetic R2 clients in the workflow tests (no real R2 is used).

The workflow reads two fixed game objects besides the prefixes a test is about:
Game-Linux/Version.txt (the build MOD plans are made for, when no snapshot exists yet) and
the owner's upload provenance (absent unless a test provides it). ``with_game_files(Fake)``
returns a subclass of a test's fake client that answers those two and passes every other
request on to the test's own fake unchanged.
"""
from __future__ import annotations

import gzip
import json

GAME_VERSION = b"1.7.5014 rev1195\r\n"
VERSION_KEY = "Game-Linux/Version.txt"
PROVENANCE_KEY = "_manifests/game-linux/source-provenance.json.gz"


def provenance_bytes(files: dict) -> bytes:
    """Provenance rows in the owner's upload format for ``{relative path: (size, sha256)}``."""
    rows = [{"key": "Game-Linux/" + rel, "size": size, "etag": "0" * 32, "sha256": digest,
             "byteVerified": True, "hashMeaning": "source-bytes", "mode": "0755"}
            for rel, (size, digest) in files.items()]
    return gzip.compress(json.dumps(rows).encode("utf-8"))


def with_game_files(fake, *, version: bytes = GAME_VERSION, provenance: bytes | None = None):
    class WithGameFiles(fake):
        exact_requests: list

        def list_exact_key(self, key):
            self.__dict__.setdefault("exact_requests", []).append(key)
            if key == VERSION_KEY:
                return [{"key": key, "size": len(version)}]
            if key == PROVENANCE_KEY and provenance is not None:
                return [{"key": key, "size": len(provenance)}]
            return []

        def get(self, key, dest, *args, **kwargs):
            if key == PROVENANCE_KEY and provenance is not None:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(provenance)
                return "downloaded"
            if key == VERSION_KEY and dest.parent.name == "game-version":
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(version)
                return "downloaded"
            return super().get(key, dest, *args, **kwargs)

    WithGameFiles.__name__ = fake.__name__
    return WithGameFiles
