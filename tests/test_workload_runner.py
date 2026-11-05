"""Synthetic contract tests for the private P4 runner; never use R2."""
import json
from hashlib import sha256
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

from tools import workload_regression as wr

RUNNER = Path(__file__).parent / "integration" / "run_workload_regression.py"


class WorkloadRunnerTests(unittest.TestCase):
    def code(self):
        return runpy.run_path(str(RUNNER))

    def test_parser_keeps_fixed_phase_and_profile(self):
        runner = self.code()
        parser = runner["parser"]()
        args = parser.parse_args(["prepare", "--profile", "S", "--private-root", "/tmp/root"])
        self.assertEqual((args.phase, args.profile), ("prepare", "S"))
        with self.assertRaises(SystemExit):
            parser.parse_args(["prepare", "--profile", "../../bad", "--private-root", "/tmp/root"])

    def test_private_workflow_uses_runner_context_only_in_steps(self):
        workflow = (RUNNER.parents[2] / ".github/workflows/linux-private-workload.yml").read_text(encoding="utf-8")
        job_header, steps = workflow.split("    steps:", 1)
        self.assertNotIn("runner.temp", job_header)
        self.assertIn("runner.temp", steps)

    def test_cow_phase_is_opt_in_and_hides_cloud_credentials(self):
        runner = self.code()
        args = runner["parser"]().parse_args(
            ["cow", "--profile", "S", "--private-root", "/tmp/root"])
        self.assertEqual(args.phase, "cow")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/"mods").mkdir()
            (root/"request.json").write_text("{}")
            (root/"profile.json").write_text(json.dumps({"profile": "S",
                "requestSha256": sha256(b"{}").hexdigest()}))
            with (
                patch.object(runner["cow"], "run_benchmark") as bench,
                patch.dict(os.environ, {"AWS_SECRET_ACCESS_KEY": "fake"}, clear=False),
            ):
                bench.side_effect = lambda private: (
                    self.assertIsNone(os.environ.get("AWS_SECRET_ACCESS_KEY")) or
                    {"status": "unsupportedFilesystem", "complete": False,
                     "samples": {"copy": 0, "reflink": 0},
                     "medianCopySeconds": None, "medianReflinkSeconds": None,
                     "reflinkSpeedupPercent": None})
                summary = runner["run_cow_profile"](root, "S")
            self.assertEqual(summary["status"], "unsupportedFilesystem")
            self.assertTrue((root/"cow-summary.json").exists())
            mount=root/"mount";mount.mkdir()
            with patch.object(runner["cow"], "run_benchmark") as bench:
                bench.return_value={"status": "unsupportedFilesystem", "complete": False,
                    "samples": {"copy": 0, "reflink": 0}, "medianCopySeconds": None,
                    "medianReflinkSeconds": None, "reflinkSpeedupPercent": None}
                (root/"cow-summary.json").unlink()
                runner["run_cow_profile"](root, "S", mount)
                self.assertEqual(bench.call_args.kwargs["btrfs_root"], mount)
            self.assertEqual(os.environ.get("AWS_SECRET_ACCESS_KEY"), None)

    def test_observation_only_counts_real_passed_results(self):
        build = self.code()["parse_measurement"]
        request = {"mods": [{"packageId": "a.mod"}, {"packageId": "b.mod"}]}
        result = {"status": "passed",
                  "modOrder": {"matches": True, "actual": ["ludeon.rimworld", "a.mod", "b.mod"]},
                  "process": {"target": {"peakRssBytes": 1234}},
                  "diagnostics": {"baselineCached": True}}
        row = build("cached-1", result, request, 2.25)
        self.assertEqual(row["elapsedSeconds"], 2.25)
        self.assertEqual(row["peakRssBytes"], 1234)
        self.assertTrue(wr.summarize_runs([row])["complete"] is False)
        self.assertNotIn("modOrder", str(row))
        result["status"] = "incomplete"
        self.assertEqual(build("cached-1", result, request, 2.25)["status"], "incomplete")

    def test_profile_pins_exact_qualified_14985_build(self):
        runner = self.code()
        runner["require_pinned_game"]({"version": "1.7.4985 rev1269"})
        for bad in ("1.7.4995 rev0", "1.7.4985", None, "", 1.7):
            with self.subTest(version=bad), self.assertRaises(ValueError):
                runner["require_pinned_game"]({"version": bad})

    def test_memory_sample_requires_both_baseline_and_target_rss(self):
        build = self.code()["parse_measurement"]
        request = {"mods": [{"packageId": "example.one"}]}
        base = {"status": "passed",
                "modOrder": {"matches": True, "actual": ["ludeon.rimworld", "example.one"]},
                "diagnostics": {"baselineCached": False},
                "process": {"target": {"peakRssBytes": 2000},
                            "baseline": {"peakRssBytes": 1400}}}
        complete = build("uncached-1", base, request, 2.0)
        self.assertEqual(complete["peakRssBytes"], 2000)
        self.assertTrue(wr.valid_measurement_row(complete, "uncached-1"))
        for missing in ("baseline", "target"):
            with self.subTest(missing=missing):
                incomplete = {**base, "process": {missing: {"peakRssBytes": 2000}}}
                row = build("uncached-1", incomplete, request, 2.0)
                self.assertIsNone(row["peakRssBytes"])
                self.assertFalse(wr.valid_measurement_row(row, "uncached-1"))
        missing_value = {**base, "process": {"target": {"peakRssBytes": 2000},
                                            "baseline": {}}}
        self.assertIsNone(build("uncached-1", missing_value, request, 2.0)["peakRssBytes"])

    def test_private_manifest_digest_is_required_and_checked_before_run(self):
        runner = self.code()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"game-snapshot").mkdir()
            (root/"request.json").write_text(json.dumps({
                "levels":["A"], "official":["Core","Royalty"],
                "mods":[{"packageId":"a.mod","target":True}]}))
            (root/"profile.json").write_text(json.dumps({"profile":"S"}))
            (root/"worker").mkdir()
            with patch.object(runner["vh"], "run_validation") as call:
                with self.assertRaises(ValueError):
                    runner["run_profile"](root,root/"worker","S")
                call.assert_not_called()
            (root/"profile.json").write_text(json.dumps({"profile":"S",
                "requestSha256":sha256(b"different request").hexdigest()}))
            with patch.object(runner["vh"], "run_validation") as call:
                with self.assertRaises(ValueError):
                    runner["run_profile"](root,root/"worker","S")
                call.assert_not_called()
            with self.assertRaises(ValueError):
                runner["publish_profile"](root,"S")

    def test_publish_keeps_first_acquisition_distinct_and_private_values_out(self):
        runner = self.code()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "request.json").write_bytes(b"{}")
            (root / "profile.json").write_text(json.dumps({
                "profile": "S",
                "requestSha256": sha256(b"{}").hexdigest(),
                "preparation": {
                    "modFetchSeconds": 7.25, "gameRuntimeFetchSeconds": 12.5,
                    "snapshotTotalSeconds": 4, "totalInitialSeconds": 24,
                    "selectedModCount": 3, "selectedModFiles": 250,
                    "selectedModBytes": 1024, "gameFiles": 1200,
                    "privatePath": "/secret/private/modfiles",
                }
            }))
            (root / "workload-rows.json").write_text("[]")
            result = runner["publish_profile"](root, "S")
            self.assertFalse(result["complete"])
            self.assertTrue(result["preparation"]["complete"])
            self.assertEqual(result["preparation"]["totalInitialSeconds"], 24)
            self.assertNotIn("/secret", json.dumps(result))
            self.assertNotIn("privatePath", json.dumps(result))

    def test_run_separates_credentials_and_never_counts_failed_rows(self):
        runner = self.code()
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "game-snapshot").mkdir()
            (root / "request.json").write_text(json.dumps({
                "recordType": "modValidationRequest", "schemaVersion": 1,
                "levels": ["A"], "official": ["Core", "Royalty"], "language": "English",
                "mods": [{"packageId": "a.mod", "target": True}]}))
            (root / "profile.json").write_text(json.dumps({"profile": "S",
                "requestSha256": sha256((root / "request.json").read_bytes()).hexdigest()}))
            worker = root / "worker"
            worker.mkdir()
            def fake_validate(snapshot, request, out, worker_dir, **kwargs):
                self.assertIsNone(os.environ.get("AWS_SECRET_ACCESS_KEY"))
                name = out.name
                calls.append((name, kwargs.get("baseline_cache")))
                return {"status": "incomplete" if name == "uncached-3" else "passed",
                        "modOrder": {"matches": True, "actual": ["a.mod"]},
                        "process": {"target": {"peakRssBytes": 900}},
                        "diagnostics": {"baselineCached": name.startswith("cached-")}}
            synthetic_clock = iter(range(1000))
            with (
                patch.object(runner["vh"], "run_validation", side_effect=fake_validate),
                patch.object(runner["time"], "monotonic", side_effect=lambda: next(synthetic_clock)),
                patch.dict(os.environ, {"AWS_SECRET_ACCESS_KEY": "fake", "R2_ENDPOINT": "https://fake.local"}),
            ):
                summary = runner["run_profile"](root, worker, "S")
            self.assertEqual([case for case, _ in calls],
                             ["uncached-1", "cache-fill", "cached-1", "uncached-2", "cached-2", "uncached-3"],
                             "stop at the first invalid sample rather than running all 11")
            self.assertEqual(len(calls), 6)
            self.assertFalse(summary["complete"])
            self.assertEqual(len(json.loads((root / "workload-rows.json").read_text())), 6)
            self.assertIsNone(summary["medianUncachedSeconds"])
            self.assertEqual(os.environ.get("AWS_SECRET_ACCESS_KEY"), None)
            self.assertTrue((root / "workload-summary.json").exists())


if __name__ == "__main__":
    unittest.main()
