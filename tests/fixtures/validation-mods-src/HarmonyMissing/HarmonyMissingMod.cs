using HarmonyLib;
using Verse;

namespace RWMT.HarmonyMissing
{
    // Deliberately never calls PatchAll: the expected patch must be reported missing.
    public class HarmonyMissingMod : Mod
    {
        public HarmonyMissingMod(ModContentPack content) : base(content)
        {
        }
    }

    [HarmonyPatch(typeof(GenText), nameof(GenText.ToSpaceList))]
    public static class ToSpaceListPatch
    {
        public static void Postfix(ref string __result)
        {
            __result += " [rwmt-missing]";
        }
    }
}
