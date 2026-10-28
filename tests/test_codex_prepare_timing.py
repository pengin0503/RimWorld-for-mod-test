"""Synthetic timing checks; no real R2 or game files are accessed."""
from types import SimpleNamespace
from unittest.mock import patch
import time

from test_validation_host import TempCase
from tools import codex_workflow as cw


class PrepareTimingTests(TempCase):
    def test_first_preparation_reports_fetch_and_snapshot_timings(self):
        version = self.fx.game / "Version.txt"

        class FakeR2:
            def list_prefix(self, prefix):
                if prefix != "Game-Linux/":
                    raise AssertionError("unexpected prefix")
                return [{"key": prefix + "Version.txt", "size": version.stat().st_size}]

            def get(self, key, dest, size, *, refresh=False):
                if key != "Game-Linux/Version.txt" or dest != version or refresh:
                    raise AssertionError("unexpected request")
                time.sleep(0.03)
                return "cached"

        args = SimpleNamespace(private_root=self.root, aws="aws", refresh=False)
        with patch.object(cw, "r2_client", return_value=FakeR2()):
            result = cw.prepare(args)

        self.assertEqual(result["status"], "prepared")
        self.assertEqual(result["r2"]["cached"], 1)
        self.assertIn("timings", result)
        timings = result["timings"]
        self.assertEqual(set(timings), {"fetchSeconds", "snapshotCopySeconds",
                                        "snapshotHashSeconds", "snapshotTotalSeconds",
                                        "totalSeconds"})
        self.assertGreaterEqual(timings["fetchSeconds"], 0.025)
        self.assertGreaterEqual(timings["totalSeconds"], timings["fetchSeconds"])
        for value in timings.values():
            self.assertIsInstance(value, (int, float))
            self.assertGreaterEqual(value, 0)

        with patch.object(cw, "r2_client", side_effect=AssertionError("unexpected R2 call")):
            reused = cw.prepare(args)
        self.assertEqual(reused["status"], "snapshotReused")

