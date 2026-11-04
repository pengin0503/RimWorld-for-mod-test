#!/usr/bin/env python3
"""Private-port build preparation. Operates only on a throwaway checkout."""
from pathlib import Path
import re
import sys

root = Path(sys.argv[1]).resolve()
bfm_file = Path(sys.argv[2]).resolve() / "BetterFloatMenu" / "BetterFloatMenu.cs"
assert bfm_file.is_file(), bfm_file
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
    text = re.sub(r'<PackageReference Include="BetterFloatMenu" Version="[^"]+"\s*/>', '', text)
    for old in ["1.6.4871","1.6.4870"]:
        text = text.replace(old, "1.7.4995-unstable")
    text = re.sub(r'(<PackageReference Include="Lib\.Harmony" Version=")[^"]+(")',r'\g<1>3.0.0-rc.3\2',text)
    # Remove package assemblies carrying older Mono/Unity dependencies.
    text = text.replace('Include="Unity.Newtonsoft.Json" Version="7.0.0"', 'Include="Newtonsoft.Json" Version="13.0.3"')
    text = text.replace("<TargetFramework>net472</TargetFramework>", "<TargetFramework>net10.0</TargetFramework>")
    text = text.replace("<TargetFramework>net48</TargetFramework>", "<TargetFramework>net10.0</TargetFramework>")
    text = text.replace("<TreatWarningsAsErrors>true</TreatWarningsAsErrors>", "<TreatWarningsAsErrors>false</TreatWarningsAsErrors>")
    text = re.sub(r'<ItemGroup>\s*<Reference Include="0ColourPicker">.*?</Reference>\s*</ItemGroup>', '', text, flags=re.S)
    if text != before:
        project.write_text(text, encoding="utf-8")
        count += 1
print("Updated",count,"C# projects and shared props")
# The 1.7 Unity API is provided by UnityStubs/Waylith; the pre-built
# BetterFloatMenu package retains an incompatible old UnityEngine.CoreModule
# identity. Compile Epicguru's MIT-licensed 1.7 source against the same refs.
bfm_target = sources / "AnimationMod" / "EpicUtils" / "BetterFloatMenu.cs"
bfm_target.parent.mkdir(parents=True, exist_ok=True)
bfm_target.write_bytes(bfm_file.read_bytes())
print("Vendored BetterFloatMenu source (MIT) for consistent type identity")
# The old 0ColourPicker binary also binds UnityEngine.CoreModule; use a tiny
# 1.7-native replacement for only the API this mod actually calls.
picker = sources / "AnimationMod" / "ColourPicker" / "Dialog_ColourPicker.cs"
picker.parent.mkdir(parents=True, exist_ok=True)
picker.write_text(r"""
using System;
using UnityEngine;
using Verse;
namespace ColourPicker
{
    public sealed class Dialog_ColourPicker : Window
    {
        private readonly Action<Color> onSelected;
        private Color selected;
        public bool autoApply = true;

        public Dialog_ColourPicker(Color initial, Action<Color> onColor)
        {
            selected = initial;
            onSelected = onColor;
            doCloseX = true;
            closeOnCancel = true;
            closeOnAccept = false;
            absorbInputAroundWindow = true;
            draggable = true;
        }

        public override Vector2 InitialSize => new Vector2(440f, 300f);

        public override void DoWindowContents(Rect rect)
        {
            var top = new Rect(rect.x, rect.y, rect.width, 42f);
            Widgets.DrawBoxSolid(top, selected);
            float y = top.yMax + 8f;
            selected.r = Channel("Red", selected.r, ref y, rect);
            selected.g = Channel("Green", selected.g, ref y, rect);
            selected.b = Channel("Blue", selected.b, ref y, rect);
            selected.a = Channel("Alpha", selected.a, ref y, rect);
            if (autoApply) onSelected?.Invoke(selected);
            var buttons = new Rect(rect.x, rect.yMax-32f,rect.width, 28f);
            if (Widgets.ButtonText(buttons.LeftHalf(), "Apply"))
            {
                onSelected?.Invoke(selected);
                Close();
            }
            if (Widgets.ButtonText(buttons.RightHalf(), "Cancel"))
                Close();
        }

        private static float Channel(string label, float value, ref float y, Rect rect)
        {
            var labelRect = new Rect(rect.x, y, 65f, 26f);
            Widgets.Label(labelRect,label);
            var sliderRect = new Rect(rect.x+70f,y,rect.width-72f,24f);
            float result = Widgets.HorizontalSlider(sliderRect,value,0f,1f);
            y += 36f;
            return result;
        }
    }
}
""", encoding="utf-8")
print("Replaced .NET Framework-only 0ColourPicker dependency with a native 1.7 dialog")

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


# Native versions of small, independently verifiable 1.7 fixes. These address
# symptoms also documented by ifchen0/MeleeAnimRenderFix without bundling the
# separately licensed patch DLL or substantial sections of its source code.
amend("AnimationMod/Events/EventBase.cs",
      "Activator.CreateInstance(type) as EventBase",
      "ScriptableObject.CreateInstance(type) as EventBase",
      expected=2)
amend("AnimationMod/Events/EventBase.cs",
      "            string id = instance.EventID;\n            allBases.Add",
      "            string id = instance.EventID;\n            UnityEngine.Object.Destroy(instance);\n            allBases.Add")
amend("AnimationMod/Sweep/SweepMesh.cs",
      "        public void Rebuild()\n        {\n            Mesh.SetVertices(vertices);",
      "        public void Rebuild()\n        {\n            Mesh.Clear();\n            Mesh.SetVertices(vertices);")
amend("AnimationMod/AnimRenderer.cs",
      '            Core.Error("Started twice!");\n            return;',
      '            return;')
amend("AnimationMod/Processing/MapPawnProcessor.cs",
      "        if (targetPawn.Dead || targetPawn.Downed || targetPawn.IsInAnimation() || GrabUtility.IsBeingTargetedForGrapple(targetPawn))",
      "        if (targetPawn.Dead || targetPawn.Downed || targetPawn.IsPsychologicallyInvisible() || targetPawn.IsInAnimation() || GrabUtility.IsBeingTargetedForGrapple(targetPawn))")
amend("AnimationMod/Outcome/OutcomeUtility.cs",
      "                return Damage(attacker, target, args);",
      """                // An inventory sidearm does not expose melee verbs while the
                // primary weapon is equipped; prefer the primary or bare hands.
                var effective = args;
                if (effective.Weapon != null && effective.Weapon != attacker.equipment?.Primary)
                    effective.Weapon = attacker.equipment?.Primary;
                return Damage(attacker, target, effective);""")
print("Integrated event creation, trails, duel re-entry, invisibility, and sidearms fixes")


# Defensive preparation of the 1.7 cached pre-render results. Avoid doing
# reflection on the common path where the parameters are already populated.
amend("AnimationMod/Patches/Patch_PawnRenderer_RenderPawnAt.cs",
      "    public static Vector3 StandaloneHeadPosition;",
      """    public static Vector3 StandaloneHeadPosition;
    private static readonly System.Reflection.MethodInfo GetPreResults =
        AccessTools.Method(typeof(PawnRenderer), "ParallelGetPreRenderResults");
    private static readonly System.Reflection.MethodInfo GetDrawParams =
        AccessTools.Method(typeof(PawnRenderer), "GetDrawParms");
    private static readonly System.Reflection.PropertyInfo GetDefaultFlags =
        AccessTools.Property(typeof(PawnRenderer), "DefaultRenderFlagsNow");
    """)
amend("AnimationMod/Patches/Patch_PawnRenderer_RenderPawnAt.cs",
      "public static bool Prefix(Pawn ___pawn, PawnRenderTree ___renderTree, ref PawnRenderer.PreRenderResults ___results, ref PawnRenderer.PreRenderResults? __state)",
      "public static bool Prefix(PawnRenderer __instance, Pawn ___pawn, PawnRenderTree ___renderTree, Vector3 drawLoc, Rot4? rotOverride, bool neverAimWeapon, ref PawnRenderer.PreRenderResults ___results, ref PawnRenderer.PreRenderResults? __state)")
amend("AnimationMod/Patches/Patch_PawnRenderer_RenderPawnAt.cs",
      """        // Auto-reset AllowNext flag.
        AllowNext = false;""",
      """        // Auto-reset AllowNext flag.
        AllowNext = false;

        if (___results.parms.pawn == null)
        {
            try
            {
                __instance.EnsureGraphicsInitialized();
                if (GetPreResults != null)
                    ___results = (PawnRenderer.PreRenderResults)GetPreResults.Invoke(
                        __instance, new object[] { drawLoc, rotOverride, neverAimWeapon, true });
                if (___results.parms.pawn == null && GetDrawParams != null && GetDefaultFlags != null)
                {
                    var flags = (PawnRenderFlags)GetDefaultFlags.GetValue(__instance)
                                | PawnRenderFlags.Clothes | PawnRenderFlags.Headgear;
                    ___results.parms = (PawnDrawParms)GetDrawParams.Invoke(__instance,
                        new object[] { drawLoc, 0f, ___pawn.Rotation, __instance.CurRotDrawMode, flags });
                    ___results.valid = true;
                }
            }
            catch (System.Exception error)
            {
                Log.ErrorOnce("[Melee Animation 1.7] Render parameters unavailable: " + error,
                              0x4D413137);
            }

            // Do not feed an invalid pawn to ParallelPreDraw.
            if (___results.parms.pawn == null)
                return true;
        }""")
amend("AnimationMod/Patches/Patch_PawnRenderer_RenderPawnAt.cs",
      """        if (NextDrawMode == DrawMode.HeadStandalone)
            Patch_HediffSet_HasHead.ForcedHasHeadValue = true;

        // Force RenderTree to recalculate with the new parameters.
        if (NextDrawMode == DrawMode.HeadStandalone) ___renderTree.SetDirty();
        ___renderTree.EnsureInitialized(___results.parms.flags);
        ___renderTree.ParallelPreDraw(___results.parms);

        Patch_HediffSet_HasHead.ForcedHasHeadValue = null;""",
      """        if (NextDrawMode == DrawMode.HeadStandalone)
            Patch_HediffSet_HasHead.ForcedHasHeadValue = true;

        try
        {
            if (NextDrawMode == DrawMode.HeadStandalone)
                ___renderTree.SetDirty();
            ___renderTree.EnsureInitialized(___results.parms.flags);
            ___renderTree.ParallelPreDraw(___results.parms);
        }
        finally
        {
            Patch_HediffSet_HasHead.ForcedHasHeadValue = null;
        }""")

# DrawCore is surrounded by a finally to clean up any animation that was
# already marked for destruction, even when a draw call throws.
amend("AnimationMod/AnimRenderer.cs",
      """    public void Draw(float? atTime, float dt, Action<AnimRenderer, EventBase> eventOutput, bool cullDraw, Action<Pawn, Vector2> labelDraw = null)
    {""",
      """    public void Draw(float? atTime, float dt, Action<AnimRenderer, EventBase> eventOutput, bool cullDraw, Action<Pawn, Vector2> labelDraw = null)
    {
        try
        {
            DrawCore(atTime, dt, eventOutput, cullDraw, labelDraw);
        }
        finally
        {
            if (delayedDestroy && !IsDestroyed)
            {
                try { Destroy(); }
                catch (System.Exception error)
                {
                    Core.Warn("[Melee Animation 1.7] Failed to clean up animation after draw: " + error);
                }
            }
        }
    }

    private void DrawCore(float? atTime, float dt, Action<AnimRenderer, EventBase> eventOutput, bool cullDraw, Action<Pawn, Vector2> labelDraw = null)
    {""")
print("Integrated defensive pre-render results and exception-safe animation cleanup")


# Cache lasso sight lines while keeping the tooltip and range visualization.
# Offsets are immutable snapshots for queued draw callbacks; they do not alias
# the mutable scratch array when hovering multiple menu options in one frame.
ui_file = sources / "AnimationMod/UI/DraftedFloatMenuOptionsUI.cs"
ui_code = ui_file.read_text(encoding="utf-8-sig")
begin = ui_code.index("    private static void HoverAction(Pawn pawn, string tt)")
end = ui_code.index("    private static FloatMenuOption GetDisabledExecutionOption(", begin)
replacement = r"""    private static Pawn cachedRangePawn;
    private static Map cachedRangeMap;
    private static IntVec3 cachedRangeCenter;
    private static float cachedRangeRadius = -1f;
    private static int cachedRangeFrame = -1000;
    private static IntVec3[] cachedRangeOffsets = Array.Empty<IntVec3>();
    private static readonly List<IntVec3> rangeDrawScratch = new List<IntVec3>();

    private static void HoverAction(Pawn pawn, string tt)
    {
        if (pawn is not { Spawned: true }) return;

        if (Event.current.type == EventType.Repaint && pawn.TryGetLasso() != null)
        {
            var map = pawn.Map;
            var center = pawn.Position;
            float radius = pawn.GetStatValue(AM_DefOf.AM_GrappleRadius);
            if (radius > 0f && radius <= GenRadial.MaxRadialPatternRadius)
            {
                int elapsed = Time.frameCount - cachedRangeFrame;
                bool keyMatches = cachedRangePawn == pawn && cachedRangeMap == map
                                  && cachedRangeRadius == radius;
                bool moved = cachedRangeCenter != center;
                int maxAge = moved ? 15 : 60;
                if (!keyMatches || elapsed >= maxAge || elapsed < 0)
                {
                    var offsets = new List<IntVec3>();
                    Func<IntVec3, bool> valid = c => ActionController.LOSValidator(c, map);
                    int count = GenRadial.NumCellsInRadius(radius);
                    for (int i = 0; i < count; i++)
                    {
                        var offset = GenRadial.RadialPattern[i];
                        if (GenSight.LineOfSight(center, center + offset, map, false, valid))
                            offsets.Add(offset);
                    }
                    cachedRangeOffsets = offsets.ToArray();
                    cachedRangePawn = pawn;
                    cachedRangeMap = map;
                    cachedRangeCenter = center;
                    cachedRangeRadius = radius;
                    cachedRangeFrame = Time.frameCount;
                }

                IntVec3[] drawOffsets = cachedRangeOffsets;
                pawn.GetAnimManager().AddPostDraw(() =>
                {
                    rangeDrawScratch.Clear();
                    for (int i = 0; i < drawOffsets.Length; i++)
                        rangeDrawScratch.Add(center + drawOffsets[i]);
                    if (rangeDrawScratch.Count > 0)
                        GenDraw.DrawFieldEdges(rangeDrawScratch, Color.yellow);
                });
            }
            else
            {
                // Nonstandard extreme radii retain the game's original behavior.
                pawn.GetAnimManager().AddPostDraw(() =>
                    GenDraw.DrawRadiusRing(center, radius, Color.yellow,
                        c => GenSight.LineOfSight(center, c, map, false,
                            c2 => ActionController.LOSValidator(c2, map))));
            }
        }

        if (tt != null)
        {
            Vector2 mouse = Event.current.mousePosition;
            TooltipHandler.TipRegion(new Rect(mouse.x-1f,mouse.y-1f,3f,3f),tt);
        }
    }

"""
ui_file.write_text(ui_code[:begin] + replacement + ui_code[end:], encoding="utf-8")
print("Integrated bounded 1.7 lasso LOS range cache")
