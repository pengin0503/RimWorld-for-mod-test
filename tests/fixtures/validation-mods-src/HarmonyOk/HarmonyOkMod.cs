using System.Collections.Generic;
using HarmonyLib;
using Verse;

namespace RWMT.HarmonyOk
{
    public class HarmonyOkMod : Mod
    {
        public HarmonyOkMod(ModContentPack content) : base(content)
        {
            new Harmony("rwmodtest.harmonyok").PatchAll(typeof(HarmonyOkMod).Assembly);
        }
    }

    [HarmonyPatch(typeof(GenText), nameof(GenText.ToSpaceList))]
    public static class ToSpaceListPatch
    {
        public static void Postfix(ref string __result)
        {
            __result += " [rwmt]";
        }
    }
}
