"""The fixture matrix's rule for platforms that are not qualified yet (no game files needed)."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / 'integration'))
import run_fixture_matrix as matrix  # noqa: E402


class ExperimentalExpectationTests(unittest.TestCase):
    def test_qualified_platform_keeps_the_exact_expectation(self):
        self.assertTrue(matrix.matches('passed', [], 'passed', [], experimental=False))
        self.assertFalse(matrix.matches('passed', [], 'incomplete', ['experimental'], experimental=False))

    def test_pass_becomes_incomplete_with_only_unqualified_reasons(self):
        self.assertTrue(matrix.matches('passed', [], 'incomplete', ['experimental'], experimental=True))
        self.assertTrue(matrix.matches('passed', [], 'incomplete', ['experimental', 'mapNotQualified'], experimental=True))
        self.assertFalse(matrix.matches('passed', [], 'incomplete', ['experimental', 'newErrors'], experimental=True))
        self.assertFalse(matrix.matches('passed', [], 'passed', [], experimental=True))

    def test_failure_must_still_be_found(self):
        self.assertTrue(matrix.matches('failed', ['newErrors'], 'incomplete', ['experimental', 'newErrors'], experimental=True))
        self.assertFalse(matrix.matches('failed', ['newErrors'], 'incomplete', ['experimental'], experimental=True))

    def test_incomplete_and_blocked_keep_their_reasons(self):
        self.assertTrue(matrix.matches('incomplete', ['workerInterrupted'], 'incomplete',
                                       ['experimental', 'workerInterrupted'], experimental=True))
        self.assertTrue(matrix.matches('blocked', ['harmonyMissing'], 'blocked', ['harmonyMissing'], experimental=True))
        self.assertFalse(matrix.matches('blocked', ['harmonyMissing'], 'incomplete', ['experimental'], experimental=True))


if __name__ == '__main__':
    unittest.main()
