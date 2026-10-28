"""MOD copies must be independent and verified on both copy paths."""
import errno
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import validation_host as vh
import importlib.util

spec = importlib.util.spec_from_file_location('linux_regression', Path(__file__).parent / 'integration/run_linux_regression.py')
regression = importlib.util.module_from_spec(spec)
spec.loader.exec_module(regression)
event_spec = importlib.util.spec_from_file_location('event_regression', Path(__file__).parent / 'integration/run_event_choice.py')
event_regression = importlib.util.module_from_spec(event_spec)
event_spec.loader.exec_module(event_regression)


class ModCopyTests(unittest.TestCase):
    def test_missing_fixture_does_not_accept_worker_failure(self):
        result = {'status': 'incomplete', 'executionStatus': 'completed',
                  'stages': {'C': {'status': 'incomplete'}},
                  'reasons': [{'code': 'eventChoiceObservationIncomplete'}, {'code': 'cNotQualified'}]}
        self.assertTrue(event_regression.missing_fixture_confirmed(result))
        self.assertFalse(event_regression.missing_fixture_confirmed(dict(result, executionStatus='incomplete')))
        self.assertFalse(event_regression.missing_fixture_confirmed(dict(result,
                         reasons=result['reasons'] + [{'code': 'timeout'}])))

    def test_real_loader_order_contract(self):
        observed = {'matches': True, 'actual': ['ludeon.rimworld', 'Dependency', 'Target']}
        self.assertTrue(regression.loader_order_matches(observed, ['dependency', 'target']))
        self.assertFalse(regression.loader_order_matches(dict(observed, matches=False), ['dependency', 'target']))
        self.assertFalse(regression.loader_order_matches(observed, ['target', 'dependency']))

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
