"""Build readiness never upgrades qualification by inference."""
from pathlib import Path
import tempfile
import unittest

from tools import build_readiness as br
from tools import r2_assets


class FakeR2:
    def __init__(self, version, missing=()):
        self.version = version
        self.missing = set(missing)
        self.downloads = []
    def list_static_audit_key(self, key):
        if key in self.missing:
            return []
        return [{"key": key, "size": 32 if key.endswith("Version.txt") else 100}]
    def get(self, key, dest, size, *, refresh=False):
        self.downloads.append(key)
        Path(dest).write_bytes(self.version)
        return "downloaded"


class ReadinessTests(unittest.TestCase):
    def test_candidate_requires_exact_build_and_all_fixed_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            r2 = FakeR2(b"1.7.4995 rev1300\n")
            result = br.inspect(r2, Path(d), "1.7.4995")
            self.assertEqual(result["state"], "readyForAudit")
            self.assertFalse(result["qualified"])
            self.assertEqual(r2.downloads, ["Game-Linux/Version.txt"])
            self.assertEqual(result["listedIdentityKeys"], len(r2_assets.STATIC_AUDIT_KEYS))

    def test_old_build_is_blocked_not_auto_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            result = br.inspect(FakeR2(b"1.7.4985 rev1269\n"), Path(d), "1.7.4995")
            self.assertEqual(result["state"], "differentBuild")
            self.assertFalse(result["qualified"])

    def test_missing_or_malformed_identity_stops(self):
        with tempfile.TemporaryDirectory() as d:
            missing = next(k for k in r2_assets.STATIC_AUDIT_KEYS if k.endswith("Assembly-CSharp.dll"))
            r = br.inspect(FakeR2(b"1.7.4995 rev1300\n", missing=[missing]), Path(d), "1.7.4995")
            self.assertEqual(r["state"], "missingIdentityFiles")
            self.assertFalse(r["qualified"])
            self.assertEqual(br.inspect(FakeR2(b"garbled\n"), Path(d), "1.7.4995")["state"], "invalidVersion")

    def test_unknown_target_and_unsafe_payload_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for target in ("1.8.6000", "1.7", "1.7.4995 rev1", "latest"):
                with self.subTest(target=target), self.assertRaises(ValueError):
                    br.inspect(FakeR2(b"1.7.4995 rev1300\n"), Path(d), target)
            self.assertEqual(
                br.inspect(FakeR2(b"1.7.4995 rev1300\nEXTRA"), Path(d), "1.7.4995")["state"],
                "invalidVersion")

    def test_without_target_any_1_7_build_is_ready_but_never_qualified(self):
        with tempfile.TemporaryDirectory() as d:
            result = br.inspect(FakeR2(b"1.7.6000 rev7\r\n"), Path(d))
            self.assertEqual((result["state"], result["version"], result["buildId"], result["qualified"]),
                             ("readyForAudit", "1.7.6000 rev7", "1.7.6000-rev7", False))
            self.assertFalse(result["reviewedRecord"])
            for version in (b"1.7.4985 rev1269\n", b"1.7.5014 rev1195\r\n"):
                self.assertTrue(br.inspect(FakeR2(version), Path(d))["reviewedRecord"])
            self.assertEqual(br.inspect(FakeR2(b"1.8.100 rev1\n"), Path(d))["state"], "unsupportedFamily")

    def test_version_not_present_requires_zero_gets(self):
        with tempfile.TemporaryDirectory() as d:
            r2 = FakeR2(b"old", missing=["Game-Linux/Version.txt"])
            res = br.inspect(r2, Path(d), "1.7.4995")
            self.assertEqual(res["state"], "missingIdentityFiles")
            self.assertEqual(r2.downloads, [])


if __name__ == "__main__":
    unittest.main()
