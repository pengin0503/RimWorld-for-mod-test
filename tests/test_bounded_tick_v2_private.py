"""Private finite D v2 acceptance runner contract, synthetic only."""
import json
from pathlib import Path
import runpy
import tempfile
import unittest

RUNNER = Path(__file__).parent / "integration" / "run_bounded_tick_v2.py"


class D2PrivateRunnerTests(unittest.TestCase):
    def script(self):
        return runpy.run_path(str(RUNNER))

    def test_fixed_request_only_uses_d2_tick_values_without_fixture(self):
        m=self.script()
        req=m["request_v2"](Path("/private/target"),60,60)
        self.assertEqual(req["tests"],["bounded-tick.v2"])
        self.assertEqual(req["levels"],["A","D"])
        self.assertEqual(req["tick"],{"count":60,"observeAt":[0,60],
                                      "observers":["game.tick"]})
        self.assertEqual(req["expectations"]["tickObservations"],[
            {"tick":0,"id":"game.tick","equals":0},
            {"tick":60,"id":"game.tick","equals":60}])
        self.assertEqual(len(req["mods"]),1)

    def test_real_evidence_gates_each_expected_outcome(self):
        m=self.script()
        def result(expected=60, cached=False, actual=60, kind="completed", status="incomplete"):
            return {
                "status":status,"executionStatus":"completed",
                "reasons":[{"code":code} for code in (
                    ["experimental", "dNotQualified", "mapNotQualified"] +
                    (["tickObservationMismatch"] if kind=="failed" else []))],
                "diagnostics":{"baselineCached":cached},
                "stages":{"A":{"status":"completed"}, "map":{"status":"completed"},
                          "D":{"status":kind,"evidence":{
                    "caseId":"bounded-tick.v2","observerVersion":2,
                    "status":"completed","initialization":"gameFinalizeInitAndStartedNewGame",
                    "startTick":0,"endTick":60,"advanced":60,
                    "observations":[
                        {"tick":0,"gameTick":0,"values":{"game.tick":0}},
                        {"tick":60,"gameTick":60,"values":{"game.tick":actual}}
                    ]}}}}
        self.assertTrue(m["case_accepted"]("positive", result(), expected_cached=False))
        self.assertTrue(m["case_accepted"]("cached", result(cached=True), expected_cached=True))
        self.assertTrue(m["case_accepted"]("mismatch", result(kind="failed",actual=60), expected_cached=False))
        for changed in ({"status":"passed"}, {"executionStatus":"interrupted"}):
            bad=result();bad.update(changed)
            self.assertFalse(m["case_accepted"]("positive",bad,expected_cached=False))
        broken=result();broken["stages"]["D"]["evidence"]["observations"][1]["values"]["game.tick"]=61
        self.assertFalse(m["case_accepted"]("positive",broken,expected_cached=False))
        without=result();without["reasons"]=[]
        self.assertFalse(m["case_accepted"]("positive",without,expected_cached=False))
        for extra in ("modOrderMismatch", "loadException", "newTranslationErrors",
                      "workerExitCode", "newWarnings", "unknownUnsafeReason"):
            with self.subTest(extra=extra):
                compromised = result()
                compromised["reasons"].append({"code": extra})
                self.assertFalse(m["case_accepted"](
                    "positive", compromised, expected_cached=False))
        for stage_name in ("A", "map"):
            compromised = result()
            compromised["stages"][stage_name]["status"] = "incomplete"
            self.assertFalse(m["case_accepted"](
                "positive", compromised, expected_cached=False))
        compromised = result()
        compromised["reasons"].append({"code":"tickObservationMismatch"})
        self.assertFalse(m["case_accepted"]("positive", compromised, expected_cached=False))

    def test_public_summary_only_has_fixed_counts_and_no_game_paths(self):
        m=self.script()
        data=[{"case":"positive","ok":True,"details":"/private/game","observed":60},
              {"case":"cached","ok":True,"details":"secret","observed":60},
              {"case":"mismatch","ok":False,"details":"secret","observed":60}]
        out=m["public_summary"](data)
        self.assertFalse(out["ok"])
        self.assertEqual(out["passedCases"],2)
        self.assertNotIn("/private",json.dumps(out))
        self.assertNotIn("secret",json.dumps(out))


if __name__=="__main__":
    unittest.main()
