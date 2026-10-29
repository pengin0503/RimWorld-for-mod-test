using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using HarmonyLib;
using Verse;

namespace RWMT.TickQualification
{
    // Development-only observer. It does not initialize games or invoke ticks.
    public class ConfigDef : Def { public bool official; public int count = 600; }
    public class ProbeMod : Mod
    {
        public ProbeMod(ModContentPack content) : base(content)
        {
            new Harmony("rwmodtest.tickqualification").PatchAll(typeof(ProbeMod).Assembly);
        }
        internal static int StartedCalls, Start, Advanced;
        internal static bool InitialObserved, Finished;
        internal static ConfigDef Config => DefDatabase<ConfigDef>.GetNamed("RWMT_TickQualification");
        internal static long Counter
        {
            get
            {
                object component = Current.Game.components.Single(c => c.GetType().FullName == "RWMT.TickProbe.TickProbeComponent");
                return (long)AccessTools.Field(component.GetType(), "Counter").GetValue(component);
            }
        }
        internal static object Get(object instance, string name) => AccessTools.Property(instance.GetType(), name)?.GetValue(instance)
            ?? AccessTools.Field(instance.GetType(), name).GetValue(instance);
        internal static object Static(string type, string name) => AccessTools.Property(AccessTools.TypeByName(type), name)?.GetValue(null)
            ?? AccessTools.Field(AccessTools.TypeByName(type), name).GetValue(null);
        internal static void Emit(object row) => Log.Message("[RWMT-TICK] " + JsonSerializer.Serialize(row));
        internal static object Setup()
        {
            Map map = Find.CurrentMap;
            return new { seed = Find.World.info.seedString, tile = map.Tile.tileId, biome = map.Biome.defName,
                sizeX = map.Size.x, sizeZ = map.Size.z, generator = map.generatorDef.defName,
                mods = LoadedModManager.RunningModsListForReading.Select(m => m.PackageId).ToArray() };
        }
        internal static object View()
        {
            object driver = Static("Verse.Find", "CameraDriver");
            object pos = Get(driver, "rootPos");
            return new { width = Static("Verse.UI", "screenWidth"), height = Static("Verse.UI", "screenHeight"),
                rootSize = Get(driver, "rootSize"), x = Get(pos, "x"), z = Get(pos, "z"),
                zoom = Get(driver, "CurrentZoom").ToString() };
        }
        internal static void FixedOfficialView()
        {
            // Retain the official CameraDriver and its real predicates; freeze the
            // reference view to the product's documented player-start zoom24 context.
            object driver = Static("Verse.Find", "CameraDriver");
            AccessTools.Method(driver.GetType(), "ResetSize").Invoke(driver, null);
            object start = Static("Verse.MapGenerator", "PlayerStartSpot");
            AccessTools.Method(driver.GetType(), "JumpToCurrentMapLoc", new[] { start.GetType() }).Invoke(driver, new[] { start });
            object camera = Get(driver, "MyCamera");
            object transform = Get(camera, "transform");
            AccessTools.Property(transform.GetType(), "position").SetValue(transform, Get(driver, "rootPos"));
            AccessTools.Property(camera.GetType(), "orthographicSize").SetValue(camera, 24f);
            AccessTools.Method(AccessTools.TypeByName("Verse.UI"), "ApplyUIScale").Invoke(null, null);
        }
        internal static void Point(int relative) => Emit(new { kind = "point", relative,
            gameTick = Find.TickManager.TicksGame, counter = Counter, startedCalls = StartedCalls,
            longEvent = LongEventHandler.AnyEventNowOrWaiting, view = View(), setup = Setup() });
        internal static void Quit()
        {
            Type app = AccessTools.TypeByName("UnityEngine.Application");
            AccessTools.Method(app, "Quit", Type.EmptyTypes).Invoke(null, null);
        }
    }

    [HarmonyPatch(typeof(GameComponentUtility), nameof(GameComponentUtility.StartedNewGame))]
    public static class Started
    {
        public static void Postfix()
        {
            ProbeMod.StartedCalls++;
            ProbeMod.Start = Find.TickManager.TicksGame;
            ProbeMod.Emit(new { kind = "started", gameTick = ProbeMod.Start, counter = ProbeMod.Counter });
        }
    }

    [HarmonyPatch(typeof(TickManager), nameof(TickManager.DoSingleTick))]
    public static class TickBoundary
    {
        public static bool Prefix(ref bool __state)
        {
            __state = false;
            if (ProbeMod.Finished) return false;  // never execute count+1
            if (ProbeMod.StartedCalls != 1)
            {
                ProbeMod.Emit(new { kind = "unexpectedTickBeforeStarted" });
                return true; // observe the official startup without replacing it
            }
            if (!ProbeMod.InitialObserved)
            {
                if (ProbeMod.Config.official) ProbeMod.FixedOfficialView();
                ProbeMod.Point(0);
                ProbeMod.InitialObserved = true;
            }
            __state = true;
            return true;
        }
        public static void Postfix(bool __state)
        {
            if (!__state) return;
            ProbeMod.Advanced++;
            int n = ProbeMod.Advanced;
            if (n == 60 || n == ProbeMod.Config.count) ProbeMod.Point(n);
            if (n >= ProbeMod.Config.count)
            {
                ProbeMod.Finished = true;
                ProbeMod.Emit(new { kind = "end", advanced = n, gameTick = Find.TickManager.TicksGame, counter = ProbeMod.Counter });
                if (ProbeMod.Config.official) ProbeMod.Quit();
            }
        }
    }
}
