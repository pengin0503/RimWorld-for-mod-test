using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using Verse;

namespace RWMT.ComparisonProbe
{
    // Development-only probe for the comparison experiment against the official
    // headless boot. It logs Harmony registrations in a fixed, greppable form.
    // It is never part of a product validation run.
    [StaticConstructorOnStartup]
    public static class HarmonyRegistrationProbe
    {
        static HarmonyRegistrationProbe()
        {
            LogLoadState();
            Type harmony = GenTypes.GetTypeInAnyAssembly("HarmonyLib.Harmony");
            if (harmony == null)
            {
                Log.Message("[RWMT-PROBE] harmony=absent");
                return;
            }
            var methods = (IEnumerable<MethodBase>)harmony.GetMethod("GetAllPatchedMethods").Invoke(null, null);
            foreach (MethodBase method in methods.OrderBy(m => m.DeclaringType.FullName + "." + m.Name))
            {
                object info = harmony.GetMethod("GetPatchInfo").Invoke(null, new object[] { method });
                foreach (string kind in new[] { "Prefixes", "Postfixes", "Transpilers", "Finalizers" })
                {
                    foreach (object patch in (IEnumerable<object>)Member(info, kind))
                    {
                        string owner = (string)Member(patch, "owner");
                        MethodInfo patchMethod = (MethodInfo)Member(patch, "PatchMethod");
                        Log.Message($"[RWMT-PROBE] patch {method.DeclaringType.FullName}.{method.Name} kind={kind} owner={owner} by={patchMethod.DeclaringType.FullName}.{patchMethod.Name}");
                    }
                }
            }
            Log.Message($"[RWMT-PROBE] effect ToSpaceList='{GenText.ToSpaceList(new[] { "a", "b" })}'");
        }

        // The same facts the Worker's level A checks read, so both boots can be compared.
        private static void LogLoadState()
        {
            Log.Message("[RWMT-PROBE] mods " + string.Join(",", LoadedModManager.RunningMods.Select(m => m.PackageId.ToLowerInvariant())));
            Log.Message("[RWMT-PROBE] language " + LanguageDatabase.activeLanguage.folderName);
            ThingDef steel = DefDatabase<ThingDef>.GetNamedSilentFail("Steel");
            Log.Message($"[RWMT-PROBE] Steel deepCountPerPortion={steel.deepCountPerPortion} MarketValue={steel.statBases.First(s => s.stat.defName == "MarketValue").value.ToString("R", System.Globalization.CultureInfo.InvariantCulture)}");
            ThingDef widget = DefDatabase<ThingDef>.GetNamedSilentFail("RWMT_Widget");
            Log.Message("[RWMT-PROBE] RWMT_Widget " + (widget == null ? "absent" : "category=" + widget.thingCategories?.FirstOrDefault()?.defName));
            Log.Message("[RWMT-PROBE] keyed RWMT_Hello=" + (LanguageDatabase.activeLanguage.TryGetTextFromKey("RWMT_Hello", out TaggedString text) ? text.RawText : "<missing>"));
            Log.Message("[RWMT-PROBE] mod classes " + string.Join(",", LoadedModManager.ModHandles.Select(h => h.GetType().FullName).OrderBy(n => n)));
        }

        // Harmony exposes some of these as fields and others as properties.
        private static object Member(object target, string name)
        {
            Type type = target.GetType();
            FieldInfo field = type.GetField(name);
            return field != null ? field.GetValue(target) : type.GetProperty(name).GetValue(target);
        }
    }
}
