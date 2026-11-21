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
        # A/B qualified, map stage not (e.g. 1.7.5014 before the map comparison agreed).
        self.assertTrue(matrix.matches('passed', [], 'incomplete', ['mapNotQualified'], experimental=False,
                                       map_unqualified=True))
        self.assertFalse(matrix.matches('passed', [], 'passed', [], experimental=False, map_unqualified=True))
        self.assertFalse(matrix.matches('passed', [], 'incomplete', ['mapNotQualified', 'newErrors'], experimental=False,
                                        map_unqualified=True))
        self.assertTrue(matrix.matches('failed', ['newErrors'], 'incomplete', ['mapNotQualified', 'newErrors'],
                                       experimental=False, map_unqualified=True))
        self.assertFalse(matrix.matches('passed', [], 'incomplete', ['experimental'], experimental=False,
                                        map_unqualified=True))

    def test_failure_must_still_be_found(self):
        self.assertTrue(matrix.matches('failed', ['newErrors'], 'incomplete', ['experimental', 'newErrors'], experimental=True))
        self.assertFalse(matrix.matches('failed', ['newErrors'], 'incomplete', ['experimental'], experimental=True))

    def test_incomplete_and_blocked_keep_their_reasons(self):
        self.assertTrue(matrix.matches('incomplete', ['workerInterrupted'], 'incomplete',
                                       ['experimental', 'workerInterrupted'], experimental=True))
        self.assertTrue(matrix.matches('blocked', ['harmonyMissing'], 'blocked', ['harmonyMissing'], experimental=True))
        self.assertFalse(matrix.matches('blocked', ['harmonyMissing'], 'incomplete', ['experimental'], experimental=True))

    def test_a_broken_run_never_matches_unless_the_case_names_it(self):
        # standard-runtime-ok expects incomplete+experimental; a crashed Worker must not satisfy it.
        self.assertFalse(matrix.matches('incomplete', ['experimental'], 'incomplete',
                                        ['workerFailed', 'baselineIncomplete', 'experimental'], experimental=True))
        self.assertFalse(matrix.matches('passed', [], 'incomplete', ['experimental', 'workerResultMissing'],
                                        experimental=True))
        self.assertTrue(matrix.matches('incomplete', ['workerInterrupted', 'baselineIncomplete'], 'incomplete',
                                       ['workerInterrupted', 'baselineIncomplete', 'experimental'], experimental=True))

    def test_build_dependent_expectation_for_prepatcher_fixture(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp) / 'game'
            game.mkdir()
            self.assertEqual(matrix.expected_case('prepatcher-field', tmp)[1:3], ('failed', ['newErrors']))
            (game / 'RimWorldWaylith.PrepatcherCompat.dll').write_bytes(b'')
            self.assertEqual(matrix.expected_case('prepatcher-field', tmp)[1:3], ('passed', []))
            self.assertEqual(matrix.expected_case('ok', tmp)[1], 'passed')


if __name__ == '__main__':
    unittest.main()
