# Internal offline knowledge database (RimWorld 1.7 unstable)

## Exact supported source

Built-in knowledge covers only **Linux RimWorld 1.7.4985 rev1269**, and only facts recorded in the project's existing official-headless comparison and result contracts. It does **not** contain the game, Workshop MOD binaries, a private MOD index, game Def XML, DLL code, decompiled source or private files. It does **not** make the host playable.

The bundled catalog remains **partial**: six inspected type identifiers, five method names (only the original `Verse.GenText.ToSpaceList` entry has an observed parameter list), one field reference, one Def, one observed Harmony target, five official package identifiers and one documented warning. This is useful for testing the pipeline and specific well-established references, but is **not** an exhaustive 1.7 API/Def index. Entries carry a pointer to their provenance in the repository. Unlisted names remain **unknown**, not missing or invalid. Actual signature overload resolution, reflection behavior, XML patch application and runtime Harmony success still need the original real-game validation host.

## Use (requires only Python 3.12+, no extra packages)

~~~bash
python tools/knowledge_preflight.py validate-db
python tools/knowledge_preflight.py query --kind type --symbol Verse.GenText
python tools/knowledge_preflight.py query --kind method --symbol Verse.GenText.ToSpaceList
python tools/knowledge_preflight.py query --kind def --symbol ThingDef:Steel
python tools/knowledge_preflight.py query --kind field --symbol Verse.ThingDef.statBases
python tools/knowledge_preflight.py query --kind official --symbol ludeon.rimworld
python tools/knowledge_preflight.py query --kind issue --symbol UnityStubs.DrawTextureStub

# A local MOD available in your current workspace, e.g. a working source MOD:
python tools/knowledge_preflight.py scan --mod ./MyMod
# The same offline mode, from the normal Codex entry point:
python tools/codex_workflow.py static-preflight --mod ./MyMod

# A local MOD ZIP is also supported; no prior extraction or R2 access:
python tools/codex_workflow.py static-preflight --mod ./MyMod.zip

# Exact complete active-set assertions are opt-in; without --complete-set
# missing dependencies remain unverified, not definitely absent.
python tools/knowledge_preflight.py scan --mod ./MyMod --active ludeon.rimworld --complete-set

# Explicit structural requirements file; no game files:
python tools/knowledge_preflight.py check --requirements ./requires.json
~~~

Requirements input is a JSON object:

~~~json
{
  "schemaVersion": 1,
  "gameBuild": "1.7.4985 rev1269",
  "requires": [
    {"kind": "type", "symbol": "Verse.GenText"},
    {"kind": "method", "symbol": "Verse.GenText.ToSpaceList",
     "parameters": ["System.Collections.Generic.IEnumerable`1[System.String]"]},
    {"kind": "def", "symbol": "ThingDef:Steel"},
    {"kind": "harmony", "symbol": "Verse.GenText.ToSpaceList"}
  ]
}
~~~

- query exits 0 if the positive fact is known, 3 if unknown.
- check exits 0 only when every explicit fact is present, 3 when unknown or the batch is empty. When `parameters` is specified for a method/Harmony target, the positive entry must match the **documented exact signature**; another overload is `unknown`, not `missing`. Omitting `parameters` checks only the name, not any overload.
- scan exits 0 for staticChecksPassed, 1 for staticIssuesFound, 3 for staticIncomplete.
- input/pack rejection exits 2 (blocked). JSON output is designed for automation.

## Offline ZIP staging and what stays private

`scan --mod ./MyMod.zip` and `codex_workflow.py static-preflight --mod ./MyMod.zip` handle a **single local MOD archive**, with `About/About.xml` at the root or inside one containing directory. They use a bounded temporary staging tree (outside the repository), retaining all relative file and version-folder names but decompressing **only** the relevant About/LoadFolders and selected Defs/Patches XML. The archive's game assets, DLLs, textures and audio are never decompressed or executed. The temporary data is discarded when the scan finishes.

ZIP path traversal, symlink members, duplicate/case-ambiguous names, multi-MOD roots, unsupported entries and excessive XML/entry counts are **blocked** (exit 2) rather than silently ignored. The static result is limited to the parser and loader rules actually modeled; a valid ZIP is *not* a verified or installable MOD. These checks avoid R2 only when a local source/ZIP and static requirements are sufficient. They do not replace private-index lookup for unknown Workshop MODs, nor any A/B/C/D runtime verification.

The additional catalog entries come exclusively from `docs/research/2026-10-26-load-folder-rules.md` (inspected 1.7.4985 loader names; **name only**, no inferred overloads) and `docs/research/split-data-inventory.json` (the inspected 1.7.4985 official DLC package IDs). As before, a missing symbol is `unknown`; the catalog must not be extrapolated to later RimWorld builds.

## Interpretation and limits

The scan checks a real local MOD's About.xml, declared 1.7 support, selected 1.7 load-folder and Defs/Patches XML syntax, and duplicate local full Def declarations. The old loader policy is reused rather than inferred from a folder name. When an active MOD set is not supplied as *complete*, absent dependencies are reported only as unverified.

A query of a method or Harmony target may include the argument types actually corroborated by the documented fixture; missing overloads or return types are not inferred. A known-issue record is informational and never automatically suppresses a game warning. Unsupported but potentially valid `LoadFolders.xml` conditions are marked `staticIncomplete`, not definitely invalid, because the offline parser intentionally models only a qualified subset of loader semantics. If `--complete-set` is not supplied, supported `IfModActive`/`IfModActiveAll`/`IfModNotActive` path conditions also remain `staticIncomplete`, since unseen active MODs may change the folders inspected. Conditional `MayRequire*` Def declarations and possible duplicates are likewise uncertain, not necessarily duplicate errors. A staticChecksPassed report means **only the checks performed did not discover a problem**. It includes gameVerification=notRun, runtimeQualified=false and an explicit notChecked list. It is **not** equivalent to a game-verified passed/qualified. A correctly named Harmony target may still fail at runtime. Do not use this system as a replacement for A/B/C/D or the qualified Linux WaylithClr runtime.

Nothing here selects arbitrary Workshop MODs. Runtime selection of third-party MODs **still begins with the private user index** and then on-demand R2 retrieval under AGENTS.md. Static scanning a local MOD folder does not need that index.

## Future version packs

The built-in pack is pinned to 1.7.4985 rev1269. Unsupported builds are blocked, not silently mapped to the closest 1.7. Optional --pack-dir permits a separate exact-build pack with schema/build validation; it does not make any runtime qualified. Stable 1.7 and newer builds should each have independent evidence and tests before inclusion. Game binaries, raw source and private Workshop data must never be committed.

## Reproducibility

Run python -m unittest tests.test_knowledge_preflight -v or the existing GitHub Actions Offline input audit. All tests use synthetic fixtures and require neither R2 credentials nor a game installation.
