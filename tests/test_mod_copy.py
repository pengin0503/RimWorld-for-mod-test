"""MOD copies must be independent and verified on both copy paths."""
import errno
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import validation_host as vh


class ModCopyTests(unittest.TestCase):
    def test_copy_modes_preserve_independence_and_detect_changed_input(self):
        for clone in (False, True):
            with self.subTest(clone=clone), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source, first, second = [root / n for n in ('source', 'first', 'second')]
                source.write_bytes(b'original')
                digest = hashlib.sha256(b'original').hexdigest()
                # Simulate kernel clone without depending on the test filesystem.
                def duplicate(reader, writer):
                    if not clone:
                        raise OSError(errno.EOPNOTSUPP, 'unsupported')
                    writer.write(reader.read())
                    return True
                with mock.patch.object(vh, '_clone_mod_file', side_effect=duplicate):
                    mode = vh.copy_verified_mod_file(source, first, digest)
                    vh.copy_verified_mod_file(source, second, digest)
                    self.assertEqual(mode, 'reflink' if clone else 'copy')
                    first.write_bytes(b'modified')
                    self.assertEqual(source.read_bytes(), b'original')
                    self.assertEqual(second.read_bytes(), b'original')
                    source.write_bytes(b'changed!')
                    with self.assertRaises(vh.Blocked) as caught:
                        vh.copy_verified_mod_file(source, root / 'stale', digest)
                    self.assertEqual(caught.exception.code, 'modChanged')

    def test_failed_clone_discards_partial_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, dest = Path(tmp) / 'source', Path(tmp) / 'dest'
            source.write_bytes(b'valid')
            def partial(reader, writer):
                writer.write(b'bad trailing bytes')
                reader.read(2)
                raise OSError(errno.EXDEV, 'different filesystem')
            with mock.patch.object(vh, '_clone_mod_file', side_effect=partial):
                self.assertEqual(vh.copy_verified_mod_file(source, dest, vh.sha256_file(source)), 'copy')
            self.assertEqual(dest.read_bytes(), b'valid')

    def test_native_copy_is_verified_and_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, dest = Path(tmp) / 'source', Path(tmp) / 'dest'
            source.write_bytes(b'original')
            self.assertIn(vh.copy_verified_mod_file(source, dest, vh.sha256_file(source)), ('copy', 'reflink'))
            self.assertNotEqual(source.stat().st_ino, dest.stat().st_ino)
            dest.write_bytes(b'changed!')
            self.assertEqual(source.read_bytes(), b'original')
