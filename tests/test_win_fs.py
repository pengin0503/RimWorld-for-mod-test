"""Tests of the Windows run-directory file operations (tools/win_fs.py).

They need NTFS hard links and junctions, so they run only on Windows (public CI
windows-latest). No game file is used.
"""
from pathlib import Path
import errno
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

WINDOWS = sys.platform == 'win32'
if WINDOWS:
    from tools import win_fs

FILE_ATTRIBUTE_READONLY = 0x1


@unittest.skipUnless(WINDOWS, 'hard links and junctions are tested on Windows only')
class WinFsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.snapshot = self.root / 'snapshot'
        self.snapshot.mkdir()
        self.run = self.root / 'run'
        self.run.mkdir()

    def tearDown(self):
        for current, _, files in os.walk(self.snapshot):
            for name in files:
                os.chmod(Path(current) / name, stat.S_IREAD | stat.S_IWRITE)
        self.tmp.cleanup()

    def read_only_file(self, name, text='game'):
        path = self.snapshot / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        os.chmod(path, stat.S_IREAD)
        return path

    def test_hardlink_shares_content(self):
        source = self.read_only_file('Assembly-CSharp.dll')
        target = self.run / 'Assembly-CSharp.dll'
        self.assertEqual(win_fs.link_file(source, target), 'hardlink')
        self.assertTrue(os.path.samefile(source, target))
        self.assertEqual(target.read_text(encoding='utf-8'), 'game')

    def test_cross_volume_falls_back_to_copy(self):
        source = self.read_only_file('Assembly-CSharp.dll')
        target = self.run / 'Assembly-CSharp.dll'
        with mock.patch.object(win_fs.os, 'link', side_effect=OSError(errno.EXDEV, 'not the same device')):
            self.assertEqual(win_fs.link_file(source, target), 'copy')
        self.assertFalse(os.path.samefile(source, target))
        self.assertEqual(target.read_text(encoding='utf-8'), 'game')

    def test_existing_destination_is_not_replaced(self):
        source = self.read_only_file('Assembly-CSharp.dll')
        target = self.run / 'Assembly-CSharp.dll'
        target.write_text('other', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            win_fs.link_file(source, target)
        self.assertEqual(target.read_text(encoding='utf-8'), 'other')

    def test_junction_is_removed_without_touching_target(self):
        inside = self.read_only_file('Data/Core/About/About.xml')
        win_fs.link_dir(self.snapshot / 'Data' / 'Core', self.run / 'Core')
        self.assertTrue((self.run / 'Core' / 'About' / 'About.xml').is_file())
        win_fs.remove_tree(self.run)
        self.assertFalse(self.run.exists())
        self.assertEqual(inside.read_text(encoding='utf-8'), 'game')

    def test_cleanup_keeps_snapshot_read_only(self):
        source = self.read_only_file('Assembly-CSharp.dll')
        (self.run / 'host').mkdir()
        self.assertEqual(win_fs.link_file(source, self.run / 'host' / 'Assembly-CSharp.dll'), 'hardlink')
        (self.run / 'host' / 'written.txt').write_text('worker output', encoding='utf-8')
        win_fs.remove_tree(self.run)
        self.assertFalse(self.run.exists())
        self.assertTrue(source.is_file())
        self.assertTrue(os.stat(source).st_file_attributes & FILE_ATTRIBUTE_READONLY)
        self.assertEqual(os.stat(source).st_nlink, 1)

    def test_read_only_copy_is_removed(self):
        (self.run / 'own.txt').write_text('x', encoding='utf-8')
        os.chmod(self.run / 'own.txt', stat.S_IREAD)
        win_fs.remove_tree(self.run)
        self.assertFalse(self.run.exists())


if __name__ == '__main__':
    unittest.main()
