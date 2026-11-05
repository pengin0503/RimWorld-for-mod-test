"""D private probe JSON evidence: fail closed and never claim qualification."""
import json
import unittest
from tools import probe_observations as po


def event(tick, name, value):
    message = "RWMT-PROBE " + json.dumps({"schemaVersion": 1, "tick": tick,
                                          "id": name, "value": value})
    return json.dumps({"level": "warning", "stage": "tick", "message": message})


class ProbeObservationTests(unittest.TestCase):
    def test_multiple_typed_observations_match_without_claiming_qualification(self):
        lines = [event(0, "probe.food", 4), event(60, "probe.food", 9),
                 json.dumps({"level": "warning", "message": "unrelated"})]
        expectations = [{"tick": 0, "id": "probe.food", "equals": 4},
                        {"tick": 60, "id": "probe.food", "equals": 9}]
        r = po.evaluate_events(lines, expectations)
        self.assertEqual(r["status"], "matched")
        self.assertEqual(r["fidelity"], "experimental")
        self.assertEqual(r["source"], "untrustedProbeLog")
        self.assertEqual(len(r["checks"]), 2)

    def test_mismatch_and_missing_remain_distinct(self):
        expected = [{"tick": 60, "id": "probe.foo", "equals": 3}]
        r = po.evaluate_events([event(60, "probe.foo", 7)], expected)
        self.assertEqual(r["status"], "mismatch")
        self.assertEqual(r["checks"][0]["actual"], 7)
        r = po.evaluate_events([event(0, "probe.foo", 3)], expected)
        self.assertEqual(r["status"], "incomplete")
        self.assertIsNone(r["checks"][0]["actual"])

    def test_duplicates_or_malformed_probe_messages_reject(self):
        expected = [{"tick": 0, "id": "probe.foo", "equals": 1}]
        for lines in ([event(0, "probe.foo", 1), event(0, "probe.foo", 1)],
                      [event(0, "probe.foo", 1),
                       json.dumps({"level": "warning", "message": "RWMT-PROBE {not json"})],
                      [event(0, "probe.foo", True)],
                      [event(0, "probe.foo", 2**64)]):
            with self.subTest(lines=lines):
                self.assertEqual(po.evaluate_events(lines, expected)["status"], "incomplete")

    def test_invalid_expectations_are_not_accepted(self):
        examples = [
            [{"tick": 0, "id": "probe.foo", "equals": True}],
            [{"tick": -1, "id": "probe.foo", "equals": 0}],
            [{"tick": 0, "id": "../private", "equals": 0}],
            [{"tick": 0, "id": "probe.foo", "equals": 0}] * 2,
            [{"tick": 0, "id": "probe.foo", "equals": 2**64}],
        ]
        for data in examples:
            with self.subTest(data=data), self.assertRaises(ValueError):
                po.evaluate_events([], data)

    def test_overflow_does_not_truncate_to_false_match(self):
        expected = [{"tick": 0, "id": "probe.foo", "equals": 1}]
        self.assertEqual(po.evaluate_events([event(0, "probe.foo", 1)] * 300,
                                            expected)["status"], "incomplete")

    def test_data_is_not_reflected_from_untrusted_message(self):
        lines = [event(0, "probe.foo", 1)]
        lines[0] = lines[0].replace("RWMT-PROBE", "RWMT-PROBE", 1)
        result = po.evaluate_events(lines, [{"tick": 0, "id": "probe.foo", "equals": 1}])
        self.assertNotIn("message", str(result))
        self.assertNotIn("stage", str(result))


if __name__ == "__main__":
    unittest.main()
