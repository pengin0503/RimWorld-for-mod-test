"""Copy versus reflink full real-MOD tree benchmark: synthetic contracts."""
import math
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import cow_benchmark as cow


class SummaryTests(unittest.TestCase):
    def rows(self):
        return ([{"case": f"copy-{i}", "mode": "copy", "seconds": float(i),
                  "identical": True} for i in range(1, 6)]
                + [{"case": f"reflink-{i}", "mode": "reflink", "seconds": float(i)/2,
                    "identical": True} for i in range(1, 6)])

    def test_complete_medians_only_with_ten_integrity_checked_runs(self):
        r = cow.summarize_samples(self.rows())
        self.assertEqual(r["status"], "measured")
        self.assertTrue(r["complete"])
        self.assertEqual(r["medianCopySeconds"], 3)
        self.assertEqual(r["medianReflinkSeconds"], 1.5)
        self.assertEqual(r["samples"], {"copy": 5, "reflink": 5})

    def test_bad_and_missing_samples_never_publish_speedup(self):
        cases = [self.rows()[:-1], self.rows()+[self.rows()[0]]]
        for index, value in ((0, float("nan")), (0, 0), (5, -1)):
            rows = self.rows(); rows[index]["seconds"] = value
            cases.append(rows)
        rows = self.rows(); rows[2]["identical"] = False; cases.append(rows)
        rows = self.rows(); rows[1]["mode"] = "reflink"; cases.append(rows)
        for rows in cases:
            with self.subTest(rows=rows):
                r = cow.summarize_samples(rows)
                self.assertFalse(r["complete"])
                self.assertIsNone(r["medianCopySeconds"])
                self.assertIsNone(r["medianReflinkSeconds"])

    def test_untrusted_extra_fields_are_never_published(self):
        rows = self.rows()
        rows[0]["path"] = "/secrets/abc"
        summary = cow.summarize_samples(rows)
        self.assertNotIn("/secrets/abc", str(summary))


class SourceTreeTests(unittest.TestCase):
    def test_manifest_proves_identical_content_independent_of_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a, b = root/"first", root/"second"
            a.mkdir(); b.mkdir()
            (a/"About").mkdir(); (b/"About").mkdir()
            (a/"About"/"About.xml").write_bytes(b"content")
            (b/"About"/"About.xml").write_bytes(b"content")
            self.assertEqual(cow.manifest(a), cow.manifest(b))
            (b/"About"/"About.xml").write_bytes(b"CHANGED")
            self.assertNotEqual(cow.manifest(a), cow.manifest(b))

    def test_reject_symlink_file_or_directory_and_budget_excess(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root/"source"; source.mkdir()
            (source/"a.txt").write_text("abc")
            with self.assertRaises(ValueError):
                cow.manifest(source, max_bytes=2)
            with self.assertRaises(ValueError):
                cow.manifest(source, max_files=0)
            link = source/"link.txt"
            try:
                link.symlink_to(source/"a.txt")
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaises(ValueError):
                cow.manifest(source)

    def test_private_source_is_staged_to_dedicated_btrfs_then_compared(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"private"; root.mkdir()
            source=root/"mods"; source.mkdir()
            (source/"About").mkdir()
            (source/"About"/"About.xml").write_bytes(b"private synthetic MOD")
            mount=Path(d)/"btrfs"; mount.mkdir()
            commands=[]
            def fake_cp(args, **kwargs):
                commands.append(args)
                shutil.copytree(Path(args[-2]), Path(args[-1]), dirs_exist_ok=True)
                return SimpleNamespace(returncode=0)
            with patch.object(cow, "filesystem_type", return_value="btrfs"), \
                 patch.object(cow.subprocess, "run", side_effect=fake_cp):
                summary=cow.run_benchmark(root, btrfs_root=mount)
            self.assertTrue(summary["complete"])
            self.assertEqual(len(commands),10)
            self.assertEqual(summary["samples"],{"copy":5,"reflink":5})
            self.assertEqual(cow.manifest(source)[0][1], len(b"private synthetic MOD"))
            self.assertEqual(list(mount.iterdir()),[])

    def test_cp_modes_are_forced_and_arguments_not_shell_strings(self):
        source=Path("/private/mods")
        dest=Path("/private/scratch/trial")
        self.assertEqual(cow.cp_command(source,dest,"copy")[:3], ["cp","-a","--reflink=never"])
        self.assertEqual(cow.cp_command(source,dest,"reflink")[:3], ["cp","-a","--reflink=always"])
        with self.assertRaises(ValueError):
            cow.cp_command(source,dest,"auto")


if __name__ == "__main__":
    unittest.main()
