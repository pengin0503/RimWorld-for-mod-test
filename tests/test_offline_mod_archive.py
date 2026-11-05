"""Offline archive/knowledge preflight integration tests; synthetic content only."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

from tools import knowledge_preflight as kp
from tools import codex_workflow as cw

ABOUT = "<ModMetaData><packageId>example.ziptest</packageId><supportedVersions><li>1.7</li></supportedVersions></ModMetaData>"


class OfflineArchivePreflightTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def archive(self, members):
        path = self.root / "testmod.zip"
        with ZipFile(path, "w") as z:
            for name, payload in members:
                z.writestr(name, payload)
        return path

    def scan(self, archive, *, via_workflow=False):
        output = StringIO()
        argv = (["static-preflight", "--mod", str(archive)] if via_workflow
                else ["scan", "--mod", str(archive)])
        with redirect_stdout(output):
            with patch.object(cw, "r2_session", side_effect=AssertionError("must remain offline")):
                code = cw.main(argv) if via_workflow else kp.main(argv)
        return code, json.loads(output.getvalue())

    def test_wrapped_mod_zip_statically_scans_without_r2_or_game(self):
        archive = self.archive([
            ("Wrapped/About/About.xml", ABOUT),
            ("Wrapped/Defs/Root.xml", "<Defs><ThingDef><defName>OfflineWidget</defName></ThingDef></Defs>"),
            ("Wrapped/1.7/Defs/Present.xml", "<Defs/>"),
            ("Wrapped/1.6/Defs/Broken.xml", "<Defs><bad>"),
            ("Wrapped/Textures/large.png", b"x" * 4096),
        ])
        code, report = self.scan(archive, via_workflow=True)
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "staticChecksPassed")
        self.assertEqual(report["gameVerification"], "notRun")
        self.assertFalse(report["runtimeQualified"])
        self.assertEqual(report["statistics"]["xmlFilesChecked"], 2)
        self.assertEqual(report["localDefinitions"], [{"type": "ThingDef", "defName": "OfflineWidget"}])
        self.assertNotIn(str(archive), json.dumps(report))

    def test_zip_preserves_version_folder_even_when_only_binary_is_inside(self):
        archive = self.archive([
            ("Wrapped/About/About.xml", ABOUT),
            ("Wrapped/Defs/Root.xml", "<Defs/>"),
            ("Wrapped/1.7/Textures/icon.png", b"not examined"),
            ("Wrapped/1.6/Defs/Broken.xml", "<Defs><bad>"),
        ])
        code, report = self.scan(archive)
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "staticChecksPassed")
        self.assertEqual(report["statistics"]["xmlFilesChecked"], 1)

    def test_zip_rejects_traversal_and_multiple_mod_roots(self):
        for members in (
            [("Wrapped/About/About.xml", ABOUT), ("Wrapped/../escape.txt", "bad")],
            [("ModA/About/About.xml", ABOUT), ("ModB/About/About.xml", ABOUT)],
            [("About/About.xml", ABOUT), ("Defs/../Defs/A.xml", "<Defs/>")],
        ):
            with self.subTest(members=[m[0] for m in members]):
                code, report = self.scan(self.archive(members))
                self.assertEqual(code, 2)
                self.assertEqual(report["status"], "blocked")

    def test_zip_rejects_symlink_members(self):
        info = ZipInfo("Wrapped/Defs/External.xml")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive = self.archive([("Wrapped/About/About.xml", ABOUT), (info, "target")])
        code, report = self.scan(archive)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "blocked")

    def test_zip_rejects_duplicate_entries_and_oversized_xml(self):
        # Two entries targeting the same case-insensitive output path are unsafe.
        archive = self.archive([
            ("About/About.xml", ABOUT),
            ("Defs/One.xml", "<Defs/>"),
            ("defs/one.XML", "<Defs/>"),
        ])
        self.assertEqual(self.scan(archive)[0], 2)
        archive = self.archive([
            ("About/About.xml", ABOUT),
            ("Defs/Huge.xml", "<Defs>" + " " * 2048 + "</Defs>"),
        ])
        from tools import offline_mod_archive
        with patch.object(offline_mod_archive, "MAX_XML_BYTES", 100):
            self.assertEqual(self.scan(archive)[0], 2)

    def test_bundled_catalog_adds_only_evidence_backed_names(self):
        db = kp.load_database(build="1.7.4985 rev1269")
        for kind, name in [
            ("type", "Verse.ModContentPack"),
            ("method", "Verse.ModContentPack.InitLoadFolders"),
            ("method", "Verse.LoadFolder.ShouldLoad"),
            ("official", "ludeon.rimworld.biotech"),
            ("official", "ludeon.rimworld.odyssey"),
        ]:
            with self.subTest(kind=kind, name=name):
                entry = db.query(kind, name)
                self.assertEqual(entry["status"], "present")
                self.assertTrue(entry["source"])
                self.assertFalse(entry["runtimeVerified"])
        self.assertEqual(db.query("method", "Verse.ModContentPack.InitLoadFolders",
                                  parameters=["System.Int32"])["status"], "unknown")
        self.assertEqual(db.query("type", "Verse.NonexistentType")["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
