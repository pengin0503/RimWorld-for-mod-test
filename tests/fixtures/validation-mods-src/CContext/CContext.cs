using System;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using HarmonyLib;
using RimWorld;
using Verse;

namespace RWMT.CContext
{
    // Development-only observer. Never changes queue order or product predicates.
    public class ConfigDef : Def { public bool official; public string mode = "event"; }
    public class ProbeMod : Mod
    {
        internal static ConfigDef Config => DefDatabase<ConfigDef>.GetNamed("RWMT_CContext");
        internal static Game SavedGame;
        internal static Map SavedMap;
        internal static int Sequence, FinalizeCalls, Pane, UI, Listing, Row;
        internal static ThingDef Target;
        public ProbeMod(ModContentPack content) : base(content)
        {
            new Harmony("rwmodtest.ccontext.event").PatchAll(typeof(ProbeMod).Assembly);
        }
        internal static void Emit(object value) => Log.Message("[RWMT-CONTEXT] " + JsonSerializer.Serialize(value));
        internal static void Phase(string phase) => Emit(new { phase, seq = ++Sequence,
            sameGame = SavedGame != null && ReferenceEquals(Current.Game, SavedGame),
            sameMap = SavedMap != null && Current.Game != null && Current.Game.Maps.Contains(SavedMap),
            finalizeCalls = FinalizeCalls });
        internal static void Quit() => AccessTools.Method(AccessTools.TypeByName("UnityEngine.Application"), "Quit", Type.EmptyTypes).Invoke(null, null);
        internal static void OnPane() { Pane++; }
        internal static void OnUI() { UI++; }
        internal static void OnListing() { Listing++; }
        internal static void OnRow(object[] __args) { if (__args.Length > 0 && ReferenceEquals(__args[0], Target)) Row++; }

        internal static void Material()
        {
            Game previous = Current.Game;
            bool freshGame = false, newBill = false, returned = false, exception = false, allowed = false;
            try
            {
                var game = new Game();
                Current.Game = game;
                freshGame = !ReferenceEquals(previous, game);
                var recipe = DefDatabase<RecipeDef>.GetNamed("RWMT_BillOptions");
                Target = DefDatabase<ThingDef>.GetNamed("RWMT_BillGrain");
                Bill bill = BillUtility.MakeNewBill(recipe, null);
                newBill = bill is Bill_Production;
                var dialogType = typeof(Dialog_BillConfig);
                var pane = AccessTools.Method(dialogType, "DoIngredientConfigPane", new[] { typeof(float), typeof(float).MakeByRefType(), typeof(float), typeof(float) });
                var ui = AccessTools.GetDeclaredMethods(typeof(ThingFilterUI)).Single(m => m.Name == "DoThingFilterConfigWindow");
                var ctor = AccessTools.GetDeclaredConstructors(typeof(Listing_TreeThingFilter)).Single(c => c.GetParameters().Length == 6);
                var row = AccessTools.Method(typeof(Listing_TreeThingFilter), "DoThingDef", new[] { typeof(ThingDef), typeof(int), typeof(Map) });
                if (row == null) throw new MissingMethodException();
                var harmony = new Harmony("rwmodtest.ccontext.material");
                harmony.Patch(pane, prefix: new HarmonyMethod(typeof(ProbeMod), nameof(OnPane)));
                harmony.Patch(ui, prefix: new HarmonyMethod(typeof(ProbeMod), nameof(OnUI)));
                harmony.Patch(ctor, prefix: new HarmonyMethod(typeof(ProbeMod), nameof(OnListing)));
                harmony.Patch(row, prefix: new HarmonyMethod(typeof(ProbeMod), nameof(OnRow)));
                object dialog = Activator.CreateInstance(dialogType, new object[] { bill });
                pane.Invoke(dialog, new object[] { 0f, 0f, 400f, 400f });
                returned = true;
                var filter = (ThingFilter)AccessTools.Field(bill.GetType(), "ingredientFilter").GetValue(bill);
                allowed = filter.Allows(Target);
            }
            catch (Exception error) { exception = true; Log.Message("[RWMT-CONTEXT-PRIVATE] " + error); }
            finally { Current.Game = previous; }
            Emit(new { phase = "material", freshGame, newBill, pane = Pane, ui = UI,
                listing = Listing, row = Row, returned, exception, allowed });
        }
    }

    [StaticConstructorOnStartup]
    public static class MaterialEntry
    {
        static MaterialEntry() { if (ProbeMod.Config.official && ProbeMod.Config.mode == "material") ProbeMod.Material(); }
    }
    [HarmonyPatch(typeof(Game), nameof(Game.InitNewGame))]
    public static class Init
    {
        public static void Prefix() { if (ProbeMod.Config.mode == "event") ProbeMod.Phase("init"); }
    }
    [HarmonyPatch(typeof(Game), nameof(Game.FinalizeInit))]
    public static class Finalizing
    {
        public static void Prefix()
        {
            if (ProbeMod.Config.mode != "event" || ProbeMod.SavedMap == null) return;
            ProbeMod.FinalizeCalls++;
            ProbeMod.Phase("finalize");
        }
    }
    [HarmonyPatch(typeof(MapGenerator), nameof(MapGenerator.GenerateMap))]
    public static class Generated
    {
        public static void Postfix(Map __result)
        {
            if (ProbeMod.Config.mode != "event") return;
            ProbeMod.SavedGame = Current.Game;
            ProbeMod.SavedMap = __result;
            ProbeMod.Phase("generated");
            LongEventHandler.ExecuteWhenFinished(() =>
            {
                ProbeMod.Phase("marker");
                if (ProbeMod.Config.official) ProbeMod.Quit();
            });
        }
    }
}
