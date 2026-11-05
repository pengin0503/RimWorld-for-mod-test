"""P4 workload regression contracts; all fixtures are synthetic."""
import math
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from tools import codex_workflow as cw
from tools import workload_regression as wr


class WorkloadProfileTests(unittest.TestCase):
    def test_only_fixed_profiles(self):
        self.assertEqual(wr.profile_roots("S"), ("Vanilla Psycasts Expanded",))
        self.assertEqual(wr.profile_roots("M"), ("Vanilla Psycasts Expanded", "TD Enhancement Pack"))
        for name in ("", "../M", "all", "s", None):
            with self.subTest(name=name), self.assertRaises(ValueError):
                wr.profile_roots(name)

    def test_selected_budget_includes_cached_objects_and_all_dependencies(self):
        groups = [
            [{"key": "Workshop/1/About/About.xml", "size": 2},
             {"key": "Workshop/1/1.7/Defs/Thing.xml", "size": 10}],
            [{"key": "Workshop/2/About/About.xml", "size": 3}]
        ]
        self.assertEqual(cw.enforce_selection_caps(groups, max_selected_bytes=15,
                         max_selected_files=3, max_mods=2), {"selectedBytes": 15, "selectedFiles": 3, "selectedMods": 2})
        for limits in ({"max_selected_bytes": 14}, {"max_selected_files": 2},
                       {"max_mods": 1}):
            with self.subTest(limits=limits), self.assertRaises(cw.WorkflowError) as caught:
                cw.enforce_selection_caps(groups, **limits)
            self.assertEqual(caught.exception.code, "modSelectionBudgetExceeded")
        for invalid in (True, 0, -1, 2.5, "10"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                cw.enforce_selection_caps(groups, max_selected_bytes=invalid)

    def test_multiple_explicit_roots_are_deduplicated_case_insensitively(self):
        roots = wr.profile_roots("M")
        resolved = [("VPE", "oskarpotocki.vanillapsycastsexpanded"),
                    ("TD", "Uuugggg.td.enhancement.pack")]
        self.assertEqual(wr.explicit_root_ids(resolved), frozenset(
            ("oskarpotocki.vanillapsycastsexpanded", "uuugggg.td.enhancement.pack")))
        with self.assertRaises(ValueError):
            wr.explicit_root_ids([resolved[0], ("Again", "OSKARPOTOCKI.VANILLAPSYCASTSEXPANDED")])


class PayloadPreflightTests(unittest.TestCase):
    def test_dependency_plan_budget_stops_before_any_payload_get(self):
        xml = b"<ModMetaData><name>Example</name><packageId>author.example</packageId></ModMetaData>"
        prefix = "Workshop/1234567890/"
        about = prefix + "About/About.xml"
        payload = prefix + "1.7/Defs/Large.xml"

        class FakeR2:
            def __init__(self):
                self.downloads = []
            def list_prefix(self, value):
                if value != prefix:
                    raise AssertionError("unexpected MOD prefix")
                return [{"key": about, "size": len(xml)}, {"key": payload, "size": 2048}]
            def get(self, key, dest, size, *, refresh=False):
                self.downloads.append(key)
                if key != about:
                    raise AssertionError("payload GET occurred before workload budget")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(xml)
                return "downloaded"
            def close(self):
                pass

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = root / "index.zip"
            with ZipFile(index, "w") as archive:
                archive.writestr("mods.json", json.dumps({"schema_version": 1, "mods": [
                    {"workshop_id": "1234567890", "package_id": "author.example",
                     "name": "Example", "supported_versions": ["1.7"]}]}))
            args = SimpleNamespace(private_root=root / "private", index_zip=str(index),
                                   aws="aws", refresh=False, target="Example",
                                   local_target=None, dependency=[], official=["Core"],
                                   language="English", scope="validation")
            fake = FakeR2()
            with patch.object(cw, "r2_client", return_value=fake), self.assertRaises(cw.WorkflowError) as caught:
                cw.fetch_mods(args, max_selected_bytes=len(xml), max_selected_files=10, max_mods=1)
            self.assertEqual(caught.exception.code, "modSelectionBudgetExceeded")
            self.assertEqual(fake.downloads, [about])
            self.assertFalse((root / "private" / "request.json").exists())


class PreparationPublicationTests(unittest.TestCase):
    def sample(self):
        return {
            "modFetchSeconds": 7.25,
            "gameRuntimeFetchSeconds": 12.5,
            "snapshotTotalSeconds": 4.0,
            "totalInitialSeconds": 23.75,
            "selectedModCount": 3,
            "selectedModFiles": 250,
            "selectedModBytes": 1024,
            "gameFiles": 1200,
            "privateIndexPath": "/secret/index.zip",
        }

    def test_public_initial_preparation_is_fixed_safe_numeric_fields(self):
        summary = wr.summarize_preparation(self.sample())
        self.assertTrue(summary["complete"])
        self.assertEqual(summary["modFetchSeconds"], 7.25)
        self.assertEqual(summary["gameRuntimeFetchSeconds"], 12.5)
        self.assertEqual(summary["totalInitialSeconds"], 23.75)
        self.assertEqual(summary["selectedModCount"], 3)
        self.assertNotIn("privateIndexPath", summary)
        self.assertNotIn("/secret", str(summary))

    def test_bad_private_prep_never_publishes_fake_speed_or_sizes(self):
        for key, value in (("modFetchSeconds", float("nan")),
                           ("totalInitialSeconds", -1),
                           ("gameRuntimeFetchSeconds", True),
                           ("selectedModBytes", -1),
                           ("selectedModCount", "three"),
                           ("totalInitialSeconds", 1.0)):
            with self.subTest(key=key, value=value):
                raw = self.sample()
                raw[key] = value
                summary = wr.summarize_preparation(raw)
                self.assertFalse(summary["complete"])
                self.assertIsNone(summary["totalInitialSeconds"])
        self.assertFalse(wr.summarize_preparation({})["complete"])


class MeasurementTests(unittest.TestCase):
    def rows(self):
        return ([{"case": "uncached-" + str(i), "mode": "uncached", "status": "passed",
                  "orderMatches": True, "elapsedSeconds": float(i), "peakRssBytes": 100 + i,
                  "baselineCached": False} for i in range(1, 6)] +
                [{"case": "cache-fill", "mode": "cache-fill", "status": "passed",
                  "orderMatches": True, "elapsedSeconds": 7.0, "peakRssBytes": 111,
                  "baselineCached": False}] +
                [{"case": "cached-" + str(i), "mode": "cached", "status": "passed",
                  "orderMatches": True, "elapsedSeconds": float(i) / 2, "peakRssBytes": 100 + i,
                  "baselineCached": True} for i in range(1, 6)])

    def test_medians_exclude_cache_fill_and_are_whitelisted(self):
        summary = wr.summarize_runs(self.rows())
        self.assertTrue(summary["complete"])
        self.assertEqual(summary["medianUncachedSeconds"], 3)
        self.assertEqual(summary["medianCachedSeconds"], 1.5)
        self.assertEqual(summary["samples"], {"uncached": 5, "cached": 5})
        self.assertNotIn("cache-fill", str(summary))

    def test_failure_does_not_become_fast_success(self):
        for key, value in (("status", "incomplete"), ("orderMatches", False),
                           ("elapsedSeconds", float("nan")), ("peakRssBytes", -1)):
            with self.subTest(key=key):
                rows = self.rows()
                rows[0][key] = value
                result = wr.summarize_runs(rows)
                self.assertFalse(result["complete"])
                self.assertIsNone(result["medianUncachedSeconds"])
        rows = self.rows()
        rows[-1]["baselineCached"] = False
        self.assertFalse(wr.summarize_runs(rows)["complete"])

    def test_cache_mode_must_be_observed_not_merely_requested(self):
        rows = self.rows()
        rows[0]["baselineCached"] = True
        self.assertFalse(wr.summarize_runs(rows)["complete"])
        rows = self.rows()
        rows[5]["baselineCached"] = True
        self.assertFalse(wr.summarize_runs(rows)["complete"])

    def test_reject_duplicate_and_missing_cases(self):
        rows = self.rows()
        self.assertFalse(wr.summarize_runs(rows[:-1])["complete"])
        self.assertFalse(wr.summarize_runs(rows + [rows[0]])["complete"])

    def test_public_result_never_exposes_untrusted_values(self):
        rows = self.rows()
        rows[0]["secret"] = "PRIVATE_VALUE"
        rows[0]["path"] = "/home/private"
        s = wr.summarize_runs(rows)
        self.assertNotIn("PRIVATE_VALUE", repr(s))
        self.assertNotIn("/home/private", repr(s))

    def test_order_comparison_rejects_unexpected_or_duplicate_mods(self):
        wanted = ["a.mod", "b.mod"]
        self.assertTrue(wr.loader_order_matches({"matches": True,
            "actual": ["ludeon.rimworld", "a.mod", "b.mod"]}, wanted))
        self.assertFalse(wr.loader_order_matches({"matches": True,
            "actual": ["ludeon.rimworld", "b.mod", "a.mod"]}, wanted))
        self.assertFalse(wr.loader_order_matches({"matches": True,
            "actual": ["a.mod", "b.mod", "b.mod"]}, wanted))
        self.assertFalse(wr.loader_order_matches({"matches": False, "actual": wanted}, wanted))


if __name__ == "__main__":
    unittest.main()
