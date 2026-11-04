#!/usr/bin/env python3
"""Private-port build preparation. Operates only on a throwaway checkout."""
from pathlib import Path
import re
import sys

root = Path(sys.argv[1]).resolve()
sources = root / "Source" / "1.6"
assert (sources / "AnimationMod").is_dir(), sources

props = sources / "Directory.Build.props"
text = props.read_text(encoding="utf-8-sig")
text = text.replace("<RimworldVersion>1.6</RimworldVersion>", "<RimworldVersion>1.7</RimworldVersion>")
text = text.replace("<TargetFramework>net48</TargetFramework>", "<TargetFramework>net10.0</TargetFramework>")
text = text.replace("<TreatWarningsAsErrors>true</TreatWarningsAsErrors>", "<TreatWarningsAsErrors>false</TreatWarningsAsErrors>")
props.write_text(text, encoding="utf-8")

count = 0
for project in sources.rglob("*.csproj"):
    text = project.read_text(encoding="utf-8-sig")
    before = text
    for old in ["1.6.4871","1.6.4870"]:
        text = text.replace(old, "1.7.4995-unstable")
    text = re.sub(r'(<PackageReference Include="Lib\.Harmony" Version=")[^"]+(")',r'\g<1>3.0.0-rc.3\2',text)
    # Remove package assemblies carrying older Mono/Unity dependencies.
    text = text.replace('Include="Unity.Newtonsoft.Json" Version="7.0.0"', 'Include="Newtonsoft.Json" Version="13.0.3"')
    text = text.replace("<TargetFramework>net472</TargetFramework>", "<TargetFramework>net10.0</TargetFramework>")
    text = text.replace("<TargetFramework>net48</TargetFramework>", "<TargetFramework>net10.0</TargetFramework>")
    text = text.replace("<TreatWarningsAsErrors>true</TreatWarningsAsErrors>", "<TreatWarningsAsErrors>false</TreatWarningsAsErrors>")
    if text != before:
        project.write_text(text, encoding="utf-8")
        count += 1
print("Updated",count,"C# projects and shared props")

def amend(relative, old, new, expected=1):
    target=sources/relative
    s=target.read_text(encoding="utf-8-sig")
    n=s.count(old)
    if n!=expected:
        raise RuntimeError(f"{relative}: expected {expected} occurrences; got {n}")
    target.write_text(s.replace(old,new),encoding="utf-8")
    print("Patched", relative)

# Data-level curve fix for lazily-loaded animations, independent of JSON repair.
amend("AnimationMod/Data/Model/CurveModel.cs",
      """        return new AnimationCurve(Keyframes)
        {
            preWrapMode = PreWrapMode,
            postWrapMode = PostWrapMode
        };""",
      """        var curve = new AnimationCurve(Keyframes)
        {
            preWrapMode = PreWrapMode,
            postWrapMode = PostWrapMode
        };
        var keys = curve.keys;
        bool changed = false;
        for (int i = 0; i + 1 < keys.Length; i++)
        {
            if (!float.IsInfinity(keys[i].outTangent) || keys[i].value != keys[i + 1].value)
                continue;
            keys[i].outTangent = 0f;
            keys[i + 1].inTangent = 0f;
            changed = true;
        }
        if (changed) curve.keys = keys;
        return curve;""")
# No shared one-entry cache: the old code read the field outside its lock.
amend("AnimationMod/Patches/PatchMaster.cs",
      """        lock (key)
        {
            if (pawn == lastPawn && lastRenderer is { IsDestroyed: false })
                return lastRenderer;

            lastPawn = pawn;
            lastRenderer = AnimRenderer.TryGetAnimator(pawn);
        }

        return lastRenderer;""",
      """        return AnimRenderer.TryGetAnimator(pawn);""")
# Let vanilla rebuild only when required; severed head still needs force-dirty.
amend("AnimationMod/Patches/Patch_PawnRenderer_RenderPawnAt.cs",
      "        ___renderTree.SetDirty();",
      "        if (NextDrawMode == DrawMode.HeadStandalone) ___renderTree.SetDirty();")
print("Source-level 1.7 patches applied")
