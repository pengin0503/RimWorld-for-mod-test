"""Fail closed if the Statistics real-game smoke could expose private R2 credentials to a PR.

The fixture is workflow source text, not an execution of the private game
runtime. Tests intentionally do not resolve or print secret values.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/private-statistics-smoke.yml"


class StatisticsSmokeWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.public, cls.private = cls.source.split("\n  statistics-a-smoke:", 1)
        cls.public = cls.public.split("\n  source-build-preflight:", 1)[1]

    def test_private_workflow_never_reads_r2_credentials_on_pr(self):
        self.assertIn("pull_request:", self.source)
        self.assertIn("source-build-preflight:", self.source)
        self.assertNotIn("secrets.", self.public)
        self.assertNotIn("vars.R2_ENDPOINT", self.public)
        self.assertIn("needs: source-build-preflight", self.private)
        self.assertIn("github.ref == 'refs/heads/main'", self.private)
        self.assertIn("if: github.repository == 'pengin0503/RimWorld-for-mod-test' && github.ref == 'refs/heads/main' && github.event_name != 'pull_request'", self.private)
        self.assertNotIn("pull_request_target:", self.source)
        self.assertIn("github.repository == 'pengin0503/RimWorld-for-mod-test'", self.private)

    def test_game_resources_are_never_uploaded_or_placed_in_checkout(self):
        self.assertIn("PRIVATE_ROOT: /tmp/rwmt-statistics-private-", self.private)
        self.assertNotIn("actions/upload-artifact", self.private)
        self.assertIn('test -z "${AWS_ACCESS_KEY_ID:-}"', self.private)
        self.assertIn('test -z "${AWS_SECRET_ACCESS_KEY:-}"', self.private)

    def test_pinned_current_statistics_source_matches_preflight_and_private_gate(self):
        # Both checkouts and both immutable-commit assertions must point to
        # the same reviewed Statistics source. No hard-coded historical SHA.
        pins = re.findall(r"ref: ([0-9a-f]{40})", self.source)
        self.assertEqual(len(pins), 2)
        self.assertEqual(pins[0], pins[1])
        self.assertEqual(
            self.source.count(
                'test "$(git -C statistics-src rev-parse HEAD)" = '
                + "'" + pins[0] + "'"
            ),
            2,
        )
        self.assertIn("path: statistics-src", self.public)
        self.assertIn("RimworldStatistics.Core.Tests.csproj", self.public)
        self.assertIn("B-level actual-game Harmony registration checks", self.private)
        self.assertIn("RimworldStatistics.Patches.MainMenuButtonPatch", self.private)
        self.assertIn("RimworldStatistics.Patches.GoToMainMenuPatch", self.private)

    def test_main_only_merge_triggers_real_game_but_not_every_push(self):
        self.assertIn("push:\n    branches: [main]", self.source)
        self.assertIn("'.github/workflows/private-statistics-smoke.yml'", self.source)
        self.assertIn("workflow_dispatch:", self.source)


if __name__ == "__main__":
    unittest.main()
