"""Private Linux acceptance of genuine D v2 game.tick evidence.

A v2 *experimental* smoke/regression sequence; it cannot independently
qualify D. No raw logs, paths, MOD names, secrets or diagnostics are emitted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
from tools import bounded_tick, validation_host as vh

N=60
CASES=("positive","cached","mismatch")


def request_v2(target: Path, count: int = N, expected: int = N) -> dict:
    if count != N or expected not in (N,N-1):
        raise ValueError("only the fixed D v2 acceptance cases are supported")
    return {"recordType":"modValidationRequest","schemaVersion":1,
            "levels":["A","D"],"official":["Core"],"language":"English",
            "mods":[{"path":str(target),"target":True}],
            "map":{"seed":"RWMT-D2"},
            "tests":["bounded-tick.v2"],
            "tick":{"count":N,"observeAt":[0,N],"observers":["game.tick"]},
            "expectations":{"tickObservations":[
                {"tick":0,"id":"game.tick","equals":0},
                {"tick":N,"id":"game.tick","equals":expected}]}}


def case_accepted(case: str, result: dict, *, expected_cached: bool) -> bool:
    if case not in CASES or type(expected_cached) is not bool or not isinstance(result,dict):
        return False
    reasons=result.get("reasons") if isinstance(result.get("reasons"),list) else []
    if not all(isinstance(item, dict) and isinstance(item.get("code"), str)
               for item in reasons):
        return False
    codes={item["code"] for item in reasons}
    if len(codes)!=len(reasons):
        return False
    mismatch=case=="mismatch"
    # These codes describe the known experimental status on the pinned
    # 1.7.4985 runtime. Any other failure/incomplete reason makes this
    # specific smoke acceptance invalid, even if tick observations match.
    allowed={"experimental", "dNotQualified", "mapNotQualified"}
    if mismatch:
        allowed.add("tickObservationMismatch")
    if (not {"experimental", "dNotQualified"} <= codes
            or not codes <= allowed
            or ("tickObservationMismatch" in codes)!=mismatch):
        return False
    stages=result.get("stages")
    if not isinstance(stages,dict):
        return False
    if (not isinstance(stages.get("A"),dict)
            or stages["A"].get("status")!="completed"
            or not isinstance(stages.get("map"),dict)
            or stages["map"].get("status")!="completed"):
        return False
    stage=stages.get("D",{})
    if not isinstance(stage,dict):
        return False
    evidence=stage.get("evidence")
    cfg={"count":N,"observeAt":[0,N],"observers":["game.tick"]}
    if (result.get("status")!="incomplete" or result.get("executionStatus")!="completed"
            or "dNotQualified" not in codes
            or (result.get("diagnostics") or {}).get("baselineCached") is not expected_cached
            or not bounded_tick.evidence_complete(cfg,evidence)):
        return False
    observations=evidence["observations"]
    if (evidence["startTick"]!=0 or evidence["endTick"]!=N
            or [row["tick"] for row in observations]!=[0,N]
            or any(row["values"]["game.tick"]!=row["gameTick"] for row in observations)):
        return False
    return stage.get("status")==("failed" if mismatch else "completed")


def public_summary(rows):
    """Fixed safe schema; every row must be one of three known cases."""
    expected=set(CASES)
    seen=set()
    if not isinstance(rows,list):
        rows=[]
    safe=[]
    for row in rows:
        if not isinstance(row,dict) or row.get("case") not in expected or row.get("case") in seen:
            return {"ok":False,"passedCases":0,"totalCases":len(CASES)}
        case=row["case"]
        seen.add(case)
        safe.append((case,row.get("ok") is True))
    n=sum(1 for _,ok in safe if ok)
    return {"ok":len(safe)==len(CASES) and seen==expected and n==len(CASES),
            "passedCases":n,"totalCases":len(CASES)}


def run(snapshot: Path, worker: Path, out: Path) -> dict:
    out=Path(out).expanduser().absolute()
    # Do not follow even a symlinked parent to a checkout or shared path.
    # Only an owned fresh directory outside the repository may hold game
    # observations, raw result.json or copied private MOD inputs.
    if any(part.is_symlink() for part in (out, *out.parents)):
        raise ValueError("symlinked private output path")
    out=out.resolve()
    if out.exists() or out==REPO or REPO in out.parents or (out/".git").exists():
        raise ValueError("new private output outside checkout is required")
    if not Path(snapshot).is_dir() or not Path(worker).exists():
        raise ValueError("private snapshot or Worker is unavailable")
    out.mkdir(mode=0o700,parents=True)
    target=out/"target"
    shutil.copytree(REPO/"tests/fixtures/validation-mods/okxml",target)
    rows=[]
    for case in CASES:
        expected=N-1 if case=="mismatch" else N
        request=request_v2(target,N,expected)
        path=out/(case+".json")
        path.write_text(json.dumps(request),encoding="utf-8")
        result=vh.run_validation(snapshot,path,out/case,worker,
                                 baseline_cache=out/"baseline-cache")
        accepted=case_accepted(case,result,expected_cached=case=="cached")
        rows.append({"case":case,"ok":accepted})
        safe=public_summary(rows)
        (out/"safe-summary.json").write_text(json.dumps(safe,sort_keys=True),encoding="utf-8")
        if not accepted:
            break
    return public_summary(rows)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot",required=True,type=Path)
    p.add_argument("--worker",default=REPO/"worker/bin",type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args(argv)
    try:
        summary=run(a.snapshot,a.worker,a.out)
    except (OSError,ValueError,vh.Blocked):
        summary={"ok":False,"passedCases":0,"totalCases":len(CASES)}
    print(json.dumps(summary,sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__=="__main__":
    raise SystemExit(main())
