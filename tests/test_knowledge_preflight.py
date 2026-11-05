"""Purely synthetic, network-free tests for versioned offline knowledge checks."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import knowledge_preflight as kp


BUILD = "1.7.4985 rev1269"


class KnowledgeDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db = kp.load_database(build=BUILD)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def make_mod(self, *, version="1.7", extra="", def_xml="<Defs><ThingDef><defName>TestWidget</defName></ThingDef></Defs>"):
        mod = self.root / "SyntheticMod"
        about = mod / "About"
        defs = mod / "Defs"
        about.mkdir(parents=True)
        defs.mkdir()
        (about / "About.xml").write_text(
            "<ModMetaData><packageId>example.synthetic</packageId>"
            f"<supportedVersions><li>{version}</li></supportedVersions>{extra}</ModMetaData>",
            encoding="utf-8",
        )
        (defs / "Defs.xml").write_text(def_xml, encoding="utf-8")
        return mod

    def test_exact_pinned_build_and_future_build_are_not_assumed_compatible(self):
        self.assertEqual(self.db.metadata["gameBuild"], BUILD)
        self.assertEqual(self.db.metadata["coverage"], "partial")
        for build in ("1.7", "1.7.4995 rev1270", "1.8.0000 rev1", "../private"):
            with self.subTest(build=build):
                with self.assertRaises(kp.KnowledgeError):
                    kp.load_database(build=build)

    def test_confirmed_symbols_and_unknown_are_not_confused(self):
        for kind, symbol in (
            ("type", "Verse.GenText"),
            ("method", "Verse.GenText.ToSpaceList"),
            ("def", "ThingDef:Steel"),
            ("harmony", "Verse.GenText.ToSpaceList"),
        ):
            with self.subTest(kind=kind):
                result = self.db.query(kind, symbol)
                self.assertEqual(result["status"], "present")
                self.assertIn("source", result)
        for kind, symbol in (
            ("type", "Verse.UnverifiedType"),
            ("method", "Verse.GenText.NonexistentMethod"),
            ("def", "ThingDef:FutureThing"),
            ("harmony", "Verse.GenText.NonexistentMethod"),
        ):
            with self.subTest(kind=kind):
                self.assertEqual(self.db.query(kind, symbol)["status"], "unknown")
        self.assertEqual(self.db.query("type", "verse.gentext")["status"], "unknown")

    def test_documented_member_overload_official_and_known_issue(self):
        self.assertEqual(self.db.query("field", "Verse.ThingDef.statBases")["status"], "present")
        self.assertEqual(self.db.query("official", "ludeon.rimworld")["status"], "present")
        self.assertEqual(self.db.query("issue", "UnityStubs.DrawTextureStub")["status"], "present")
        self.assertEqual(self.db.query("field", "Verse.ThingDef.futureField")["status"], "unknown")
        method = self.db.query("method", "Verse.GenText.ToSpaceList")
        self.assertEqual(method["parameters"],
                         ["System.Collections.Generic.IEnumerable" + chr(96) + "1[System.String]"])
        self.assertFalse(method["runtimeVerified"])

    def test_valid_synthetic_mod_needs_no_game_or_r2(self):
        mod = self.make_mod()
        with patch.dict("os.environ", {"R2_ENDPOINT": "invalid-endpoint", "AWS_ACCESS_KEY_ID": "fake"}, clear=False):
            report = kp.inspect_mod(mod, self.db, active_packages=("ludeon.rimworld",))
        self.assertEqual(report["status"], "staticChecksPassed")
        self.assertEqual(report["gameVerification"], "notRun")
        self.assertFalse(report["runtimeQualified"])
        self.assertEqual(report["packageId"], "example.synthetic")
        self.assertEqual(report["statistics"]["xmlFilesChecked"], 1)
        self.assertEqual(report["localDefinitions"], [{"type": "ThingDef", "defName": "TestWidget"}])
        self.assertNotIn(str(mod), json.dumps(report))

    def test_unsupported_mod_version_is_a_definite_static_issue(self):
        report = kp.inspect_mod(self.make_mod(version="1.6"), self.db)
        self.assertEqual(report["status"], "staticIssuesFound")
        self.assertIn("versionMismatch", {i["code"] for i in report["issues"]})

    def test_malformed_xml_and_duplicate_local_def_are_reported(self):
        mod = self.make_mod(def_xml="<Defs><ThingDef>")
        report = kp.inspect_mod(mod, self.db)
        self.assertIn("invalidXml", {x["code"] for x in report["issues"]})
        (mod / "Defs" / "Defs.xml").write_text(
            "<Defs><ThingDef><defName>Same</defName></ThingDef>"
            "<ThingDef><defName>Same</defName></ThingDef></Defs>", encoding="utf-8")
        report = kp.inspect_mod(mod, self.db)
        self.assertIn("duplicateLocalDef", {x["code"] for x in report["issues"]})

    def test_effective_version_load_folders_ignore_old_broken_content(self):
        mod = self.make_mod(def_xml="<broken>")
        (mod / "1.7" / "Defs").mkdir(parents=True)
        (mod / "1.7" / "Defs" / "Good.xml").write_text("<Defs/>", encoding="utf-8")
        (mod / "1.6" / "Defs").mkdir(parents=True)
        (mod / "1.6" / "Defs" / "Broken.xml").write_text("<broken>", encoding="utf-8")
        # In the qualified 1.7 loader only 1.7 plus root is effective.
        report = kp.inspect_mod(mod, self.db)
        self.assertIn("invalidXml", {i["code"] for i in report["issues"]})
        (mod / "Defs" / "Defs.xml").write_text("<Defs/>", encoding="utf-8")
        report = kp.inspect_mod(mod, self.db)
        self.assertEqual(report["status"], "staticChecksPassed")
        self.assertEqual(report["statistics"]["xmlFilesChecked"], 2)

    def test_missing_dependency_is_uncertain_without_complete_mod_list(self):
        extra = "<modDependencies><li><packageId>other.required</packageId></li></modDependencies>"
        mod = self.make_mod(extra=extra)
        uncertain = kp.inspect_mod(mod, self.db, active_packages=("ludeon.rimworld",))
        self.assertEqual(uncertain["status"], "staticIncomplete")
        self.assertIn("dependencyNotChecked", {i["code"] for i in uncertain["issues"]})
        complete = kp.inspect_mod(mod, self.db, active_packages=("ludeon.rimworld",), complete_set=True)
        self.assertEqual(complete["status"], "staticIssuesFound")
        self.assertIn("dependencyMissing", {i["code"] for i in complete["issues"]})
        with_dependency = kp.inspect_mod(
            mod, self.db, active_packages=("ludeon.rimworld", "other.required"), complete_set=True)
        self.assertEqual(with_dependency["status"], "staticChecksPassed")

    def test_no_symlink_or_xml_entity_expansion_is_consumed(self):
        mod = self.make_mod()
        (mod / "Defs" / "Defs.xml").write_text(
            "<!DOCTYPE foo [<!ENTITY a 'bad'>]><Defs>&a;</Defs>", encoding="utf-8")
        report = kp.inspect_mod(mod, self.db)
        self.assertIn("invalidXml", {i["code"] for i in report["issues"]})
        (mod / "Defs" / "Defs.xml").write_text("<Defs/>", encoding="utf-8")
        linked = mod / "Defs" / "Extra.xml"
        try:
            linked.symlink_to(mod / "Defs" / "Defs.xml")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable on this platform")
        report = kp.inspect_mod(mod, self.db)
        self.assertIn("unsafeFile", {i["code"] for i in report["issues"]})

    def test_unsupported_but_safe_loadfolders_condition_is_incomplete_not_incompatible(self):
        mod = self.make_mod()
        (mod / "LoadFolders.xml").write_text(
            "<loadFolders><v1.7><li IfUnrecognized='flag'>/</li></v1.7></loadFolders>",
            encoding="utf-8")
        report = kp.inspect_mod(mod, self.db)
        self.assertEqual(report["status"], "staticIncomplete")
        self.assertIn("unsupportedLoaderMetadata", {r["code"] for r in report["issues"]})
        self.assertNotIn("invalidMetadata", {r["code"] for r in report["issues"]})
        (mod / "LoadFolders.xml").write_text("<loadFolders><bad", encoding="utf-8")
        report = kp.inspect_mod(mod, self.db)
        self.assertEqual(report["status"], "staticIssuesFound")
        self.assertIn("invalidMetadata", {r["code"] for r in report["issues"]})

    def test_empty_batch_and_unverified_method_overload_cannot_pass(self):
        req = self.root / "requires.json"
        def run(rows):
            req.write_text(json.dumps({"schemaVersion": 1, "gameBuild": BUILD,
                                       "requires": rows}), encoding="utf-8")
            return kp.check_requirements(req, self.db)
        self.assertEqual(run([])["status"], "staticIncomplete")
        method = {"kind": "method", "symbol": "Verse.GenText.ToSpaceList",
                  "parameters": ["System.Collections.Generic.IEnumerable" + chr(96) + "1[System.String]"]}
        report = run([method])
        self.assertEqual(report["status"], "staticChecksPassed")
        self.assertEqual(report["counts"], {"present": 1, "unknown": 0})
        method["parameters"] = ["System.Int32"]
        report = run([method])
        self.assertEqual(report["status"], "staticIncomplete")
        self.assertEqual(report["counts"], {"present": 0, "unknown": 1})
        self.assertEqual(report["results"][0]["status"], "unknown")
        with self.assertRaises(kp.KnowledgeError):
            run([{"kind": "def", "symbol": "ThingDef:Steel", "parameters": []}])
        with self.assertRaises(kp.KnowledgeError):
            run([{"kind": "method", "symbol": "Verse.GenText.ToSpaceList",
                  "parameters": ["Unknown\x00"]}])

    def test_unread_large_textures_do_not_exceed_xml_scan_byte_budget(self):
        mod = self.make_mod()
        textures = mod / "Textures"
        textures.mkdir()
        (textures / "huge.dds").write_bytes(b"x" * 4097)
        # Only About + selected Defs/Patches are opened in static mode.
        with patch.object(kp, "MAX_INPUT_BYTES", 1024):
            result = kp.inspect_mod(mod, self.db)
        self.assertEqual(result["status"], "staticChecksPassed")
        self.assertEqual(result["statistics"]["xmlFilesChecked"], 1)
        self.assertEqual(result["statistics"]["filesConsidered"], 3)

    def test_loadfolders_xml_has_size_limit_before_read(self):
        mod = self.make_mod()
        # A valid document that exceeds the scanner's artificially tight
        # per-file limit, without allocating huge files in CI.
        document = "<loadFolders><v1.7><li>/</li></v1.7></loadFolders>"
        (mod / "LoadFolders.xml").write_text(document + " " * 200, encoding="utf-8")
        with patch.object(kp, "MAX_XML_BYTES", 150):
            result = kp.inspect_mod(mod, self.db)
        self.assertEqual(result["status"], "staticIssuesFound")
        self.assertIn("invalidMetadata", {issue["code"] for issue in result["issues"]})

    def test_conditional_loadfolders_require_complete_active_set_for_clean_result(self):
        mod = self.make_mod()
        (mod / "Conditional" / "Defs").mkdir(parents=True)
        (mod / "Conditional" / "Defs" / "Broken.xml").write_text("<broken>", encoding="utf-8")
        (mod / "LoadFolders.xml").write_text(
            "<loadFolders><v1.7><li>/</li>"
            "<li IfModActive='other.required'>Conditional</li>"
            "</v1.7></loadFolders>", encoding="utf-8")
        incomplete = kp.inspect_mod(mod, self.db)
        self.assertEqual(incomplete["status"], "staticIncomplete")
        self.assertIn("conditionalLoadFoldersNotChecked",
                      {item["code"] for item in incomplete["issues"]})
        active = kp.inspect_mod(mod, self.db, active_packages=("other.required",), complete_set=True)
        self.assertEqual(active["status"], "staticIssuesFound")
        self.assertIn("invalidXml", {item["code"] for item in active["issues"]})
        excluded = kp.inspect_mod(mod, self.db, complete_set=True)
        self.assertEqual(excluded["status"], "staticChecksPassed")

    def test_conditional_duplicate_definitions_cannot_be_certified_invalid(self):
        mod = self.make_mod(def_xml=(
            "<Defs><ThingDef MayRequire='foo.optional'><defName>Same</defName></ThingDef>"
            "<ThingDef MayRequire='bar.optional'><defName>Same</defName></ThingDef></Defs>"
        ))
        result = kp.inspect_mod(mod, self.db)
        self.assertEqual(result["status"], "staticIncomplete")
        self.assertIn("conditionalDefDuplicateNotChecked",
                      {issue["code"] for issue in result["issues"]})
        self.assertNotIn("duplicateLocalDef", {issue["code"] for issue in result["issues"]})

    def test_catalog_rejects_duplicate_and_untrusted_completeness(self):
        pack = self.root / "pack"
        pack.mkdir()
        manifest = {
            "schemaVersion": 1, "gameBuild": BUILD, "coverage": "partial",
            "gameVersion": "1.7", "source": "synthetic-test",
            "collections": {name: name + ".json" for name in kp.COLLECTIONS.values()},
        }
        (pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        for key in kp.COLLECTIONS.values():
            (pack / (key + ".json")).write_text("[]", encoding="utf-8")
        self.assertEqual(kp.load_database(pack_dir=pack).query("type", "Anything")["status"], "unknown")
        (pack / "types.json").write_text(json.dumps([
            {"symbol": "Verse.A", "source": "test"}, {"symbol": "Verse.A", "source": "test"}]), encoding="utf-8")
        with self.assertRaises(kp.KnowledgeError):
            kp.load_database(pack_dir=pack)
        manifest["coverage"] = "complete"
        (pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(kp.KnowledgeError):
            kp.load_database(pack_dir=pack)

    def test_cli_query_and_scan_are_machine_readable(self):
        output = StringIO()
        with redirect_stdout(output):
            exit_code = kp.main(["query", "--build", BUILD, "--kind", "type", "--symbol", "Verse.GenText"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "present")
        output = StringIO()
        with redirect_stdout(output):
            exit_code = kp.main(["query", "--build", BUILD, "--kind", "type", "--symbol", "Verse.Unknown"])
        self.assertEqual(exit_code, 3)
        self.assertEqual(json.loads(output.getvalue())["status"], "unknown")
        mod = self.make_mod()
        output = StringIO()
        with redirect_stdout(output):
            exit_code = kp.main(["scan", "--build", BUILD, "--mod", str(mod)])
        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(output.getvalue())["gameVerification"], "notRun")


    def test_batch_requirements_return_verified_and_unknown_not_false_missing(self):
        requirements = self.root / "requires.json"
        requirements.write_text(json.dumps({
            "schemaVersion": 1, "gameBuild": BUILD,
            "requires": [{"kind": "type", "symbol": "Verse.GenText"},
                         {"kind": "def", "symbol": "ThingDef:FutureThing"}],
        }), encoding="utf-8")
        report = kp.check_requirements(requirements, self.db)
        self.assertEqual(report["status"], "staticIncomplete")
        self.assertEqual(report["counts"], {"present": 1, "unknown": 1})
        self.assertFalse(report["runtimeQualified"])
        output = StringIO()
        with redirect_stdout(output):
            code = kp.main(["check", "--build", BUILD, "--requirements", str(requirements)])
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(output.getvalue())["counts"]["unknown"], 1)
        requirements.write_text(json.dumps({
            "schemaVersion": 1, "gameBuild": BUILD, "requires": [],
            "extra": "not accepted",
        }), encoding="utf-8")
        with self.assertRaises(kp.KnowledgeError):
            kp.check_requirements(requirements, self.db)

    def test_explicit_newer_build_pack_is_opt_in_never_fallback(self):
        import shutil
        folder = self.root / "later"
        shutil.copytree(kp.DATABASE_ROOT / "1.7.4985-rev1269", folder)
        manifest = json.loads((folder / "manifest.json").read_text())
        manifest["gameBuild"] = "1.7.5000 rev1"
        (folder / "manifest.json").write_text(json.dumps(manifest))
        db = kp.load_database(build="1.7.5000 rev1", pack_dir=folder)
        self.assertEqual(db.metadata["gameBuild"], "1.7.5000 rev1")
        with self.assertRaises(kp.KnowledgeError):
            kp.load_database(build=BUILD, pack_dir=folder)

    def test_real_cli_process_without_game_files_or_r2_credentials(self):
        """Exercise both Python script entrypoints, not only direct module imports."""
        repository = Path(__file__).resolve().parents[1]
        for command, expected_record in (
            ([sys.executable, str(repository / "tools" / "knowledge_preflight.py"),
              "validate-db"], "offlineKnowledgePackStatus"),
            ([sys.executable, str(repository / "tools" / "codex_workflow.py"),
              "static-preflight", "--mod", str(self.make_mod())],
             "modKnowledgePreflight"),
        ):
            with self.subTest(command=command[1].rsplit("/", 1)[-1]):
                result = subprocess.run(
                    command, cwd=repository, capture_output=True, text=True,
                    timeout=20, check=False)
                self.assertEqual(result.returncode, 0, result.stderr[-600:])
                report = json.loads(result.stdout)
                self.assertEqual(report["recordType"], expected_record)
                self.assertEqual(report["gameVerification"], "notRun")

    def test_existing_cloud_orchestrator_can_run_standalone_static_first(self):
        from tools import codex_workflow as cw
        mod = self.make_mod()
        output = StringIO()
        with patch.object(cw, "r2_session", side_effect=AssertionError("network must never run")):
            with redirect_stdout(output):
                code = cw.main(["static-preflight", "--build", BUILD, "--mod", str(mod)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["gameVerification"], "notRun")


if __name__ == "__main__":
    unittest.main()
