"""Synthetic contract tests for the private P4 runner; never use R2."""
import json
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
            (root/"profile.json").write_text(json.dumps({"profile": "S"}))
            (root/"mods").mkdir()
            (root/"request.json").write_text("{}")
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
            (root / "profile.json").write_text(json.dumps({"profile": "S"}))
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
            with patch.object(runner["vh"], "run_validation", side_effect=fake_validate), \
                 patch.dict(os.environ, {"AWS_SECRET_ACCESS_KEY": "fake", "R2_ENDPOINT": "https://fake.local"}):
                summary = runner["run_profile"](root, worker, "S")
            self.assertEqual(len(calls), 11)
            self.assertFalse(summary["complete"])
            self.assertIsNone(summary["medianUncachedSeconds"])
            self.assertEqual(os.environ.get("AWS_SECRET_ACCESS_KEY"), None)
            self.assertTrue((root / "workload-summary.json").exists())


if __name__ == "__main__":
    unittest.main()
