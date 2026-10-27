"""The GUI explains every reason code the Controller can write (no game files needed)."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
# Codes the Controller builds at run time rather than writing literally.
DYNAMIC = {'workerFailed', 'workerInterrupted', 'workerAdaptermismatch', 'workerUnknown',  # worker<executionStatus>
           'timeout', 'memoryLimit', 'logLimit',  # process killedFor
           'workerResultMissing', 'workerResultUnreadable', 'workerResultInvalid', 'workerResultStale',
           'runningModsError', 'modOrderError', 'checksError', 'activeLanguageError', 'translationErrorsError'}


class ReasonCatalogSyncTests(unittest.TestCase):
    def test_gui_reason_catalog_covers_controller_codes(self):
        source = (ROOT / 'tools' / 'validation_host.py').read_text(encoding='utf-8')
        literal = set(re.findall(r"'code': '([a-zA-Z]+)'", source)) | set(re.findall(r"Blocked\('([a-zA-Z]+)'", source))
        catalog = (ROOT / 'gui' / 'RimWorldValidation.Gui.Model' / 'ReasonCatalog.cs').read_text(encoding='utf-8')
        explained = set(re.findall(r'\["([a-zA-Z]+)"\] =', catalog))
        self.assertGreater(len(literal), 40)
        self.assertEqual(sorted((literal | DYNAMIC) - explained), [])
        self.assertEqual(sorted(explained - literal - DYNAMIC), [])

    def test_dynamic_codes_still_exist_in_the_controller(self):
        source = (ROOT / 'tools' / 'validation_host.py').read_text(encoding='utf-8')
        self.assertIn("f'worker{worker.get(\"executionStatus\", \"unknown\").capitalize()}'", source)
        for code in ('timeout', 'memoryLimit', 'logLimit', 'workerResultStale', 'translationErrorsError'):
            self.assertIn(f"'{code}'", source)


class ProgressLogSyncTests(unittest.TestCase):
    def test_gui_describes_every_progress_kind(self):
        source = (ROOT / 'tools' / 'validation_host.py').read_text(encoding='utf-8')
        kinds = set(re.findall(r"progress\('([a-zA-Z]+)'", source))
        log = (ROOT / 'gui' / 'RimWorldValidation.Gui.Model' / 'ProgressLog.cs').read_text(encoding='utf-8')
        described = set(re.findall(r'"([a-zA-Z]+)" =>', log))
        self.assertGreater(len(kinds), 10)
        self.assertEqual(sorted(kinds - described), [])


if __name__ == '__main__':
    unittest.main()
