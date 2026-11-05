"""Bounded tick v2 registry and evidence contract (synthetic only)."""
from pathlib import Path
import unittest
from tools import bounded_tick
from tools import validation_host as vh


def request_v2():
    return {"recordType": "modValidationRequest", "schemaVersion": 1,
            "levels": ["A", "D"],
            "mods": [{"path": "mod", "target": True}],
            "map": {"seed": "RWMT-v2"},
            "tests": ["bounded-tick.v2"],
            "tick": {"count": 60, "observeAt": [0, 60], "observers": ["game.tick"]},
            "expectations": {"tickObservations": [
                {"tick": 0, "id": "game.tick", "equals": 1000},
                {"tick": 60, "id": "game.tick", "equals": 1060}]}}


def evidence_v2():
    return {"caseId": "bounded-tick.v2", "observerVersion": 2,
            "initialization": "gameFinalizeInitAndStartedNewGame",
            "status": "completed", "startTick": 1000, "endTick": 1060, "advanced": 60,
            "observations": [{"tick": n, "gameTick": 1000+n,
                              "values": {"game.tick": 1000+n}} for n in (0,60)]}


class TickV2Tests(unittest.TestCase):
    def test_registered_game_observer_is_accepted_but_experimental(self):
        r = vh.validate_request(request_v2(), Path("/tmp"))
        self.assertEqual(r["tick"]["observers"], ["game.tick"])
        self.assertEqual(bounded_tick.case_id(r["tick"]), "bounded-tick.v2")
        self.assertEqual(bounded_tick.observer_version(r["tick"]), 2)
        stage, incomplete, failed = vh.evaluate_tick(r, evidence_v2())
        self.assertEqual(stage["status"], "completed")
        self.assertEqual(stage["fidelity"], "experimental")
        self.assertIn("dNotQualified", [x["code"] for x in incomplete])
        self.assertFalse(failed)

    def test_unknown_and_duplicate_v2_observer_requests_are_rejected(self):
        for observers in ([], ["game.foo"], ["fixture.counter","fixture.counter"],
                          ["game.tick","unknown"], "game.tick", [True]):
            r=request_v2();r["tick"]["observers"]=observers
            with self.subTest(observers=observers), self.assertRaises(vh.RequestError):
                vh.validate_request(r, Path("/tmp"))
        r=request_v2();r["tick"]["observers"]=["fixture.counter"]
        with self.assertRaises(vh.RequestError):
            vh.validate_request(r, Path("/tmp"))
        r=request_v2();r["tick"]["observers"]=["game.tick"]
        r["tests"]=["bounded-tick.v1"]
        with self.assertRaises(vh.RequestError):
            vh.validate_request(r, Path("/tmp"))

    def test_v1_and_v2_never_share_cached_result_identity(self):
        v1={"count": 60,"observeAt": [0,60]}
        v2={"count": 60,"observeAt": [0,60],"observers":["game.tick"]}
        self.assertNotEqual(bounded_tick.cache_identity(v1), bounded_tick.cache_identity(v2))
        self.assertNotEqual(bounded_tick.observer_version(v1), bounded_tick.observer_version(v2))
        forged=evidence_v2();forged["caseId"]="bounded-tick.v1"
        self.assertFalse(bounded_tick.evidence_complete(v2, forged))
        forged=evidence_v2();forged["observerVersion"]=1
        self.assertFalse(bounded_tick.evidence_complete(v2, forged))

    def test_forged_missing_and_failed_v2_observation(self):
        r=vh.validate_request(request_v2(), Path("/tmp"))
        request_wrong=request_v2()
        request_wrong["expectations"]["tickObservations"][1]["equals"]=1059
        stage, incomplete, failed=vh.evaluate_tick(
            vh.validate_request(request_wrong, Path("/tmp")), evidence_v2())
        self.assertEqual(stage["status"],"failed")
        self.assertEqual(failed[0]["code"], "tickObservationMismatch")
        forged=evidence_v2()
        forged["observations"][1]["values"]["game.tick"]=1059
        self.assertFalse(bounded_tick.evidence_complete(r["tick"],forged))
        for mutate in (lambda e:e["observations"][0]["values"].update(other=1),
                       lambda e:e["observations"].pop(),
                       lambda e:e.update(advanced=59),
                       lambda e:e["observations"][0]["values"].update({"game.tick":True})):
            forged=evidence_v2();mutate(forged)
            with self.subTest(evidence=forged):
                self.assertFalse(bounded_tick.evidence_complete(r["tick"],forged))


if __name__ == "__main__":
    unittest.main()
