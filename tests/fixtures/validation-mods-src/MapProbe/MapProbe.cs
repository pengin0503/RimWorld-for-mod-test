using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using HarmonyLib;
using RimWorld;
using Verse;

namespace RWMT.MapProbe
{
    // Development-only probe for the map comparison experiment. Loaded into both
    // the official quick test (-headless -quicktest) and the product's map stage,
    // it logs a fingerprint of the generated map in a fixed, greppable form.
    // In the official run only, it makes the quick test reproducible: the world
    // seed string becomes "rwmt" and the setup runs under the same Rand state the
    // product's map stage pushes (FNV-1a of the seed), until the map is generated.
    public class MapProbeMod : Mod
    {
        public const string Seed = "rwmt";
        internal static bool officialQuickTest;

        public MapProbeMod(ModContentPack content) : base(content)
        {
            new Harmony("rwmodtest.mapprobe").PatchAll(typeof(MapProbeMod).Assembly);
        }

        internal static int StableHash(string text)
        {
            unchecked
            {
                uint hash = 2166136261;
                foreach (char c in text)
                {
                    hash = (hash ^ c) * 16777619;
                }
                return (int)hash;
            }
        }
    }

    // Root_Play is a MonoBehaviour (UnityStubs), which the fixtures do not reference.
    [HarmonyPatch]
    public static class QuickTestSeed
    {
        public static MethodBase TargetMethod() => AccessTools.Method("Verse.Root_Play:SetupForQuickTestPlay");

        public static void Prefix()
        {
            MapProbeMod.officialQuickTest = true;
            Rand.PushState(MapProbeMod.StableHash(MapProbeMod.Seed));
        }
    }

    [HarmonyPatch(typeof(GenText), nameof(GenText.RandomSeedString))]
    public static class FixedSeedString
    {
        public static bool Prefix(ref string __result)
        {
            if (!MapProbeMod.officialQuickTest)
            {
                return true;
            }
            __result = MapProbeMod.Seed;
            return false;
        }
    }

    [HarmonyPatch(typeof(MapGenerator), nameof(MapGenerator.GenerateMap))]
    public static class Fingerprint
    {
        public static void Postfix(Map __result)
        {
            if (MapProbeMod.officialQuickTest)
            {
                Rand.PopState();
                MapProbeMod.officialQuickTest = false;
            }
            Map map = __result;
            Log.Message($"[RWMT-PROBE] map world seed={Find.World.info.seedString} coverage={Find.World.info.planetCoverage.ToString("R", System.Globalization.CultureInfo.InvariantCulture)} tile={map.Tile.tileId} biome={map.Biome.defName} size={map.Size.x}x{map.Size.z} generator={map.generatorDef.defName}");
            Log.Message("[RWMT-PROBE] map terrain sha=" + Sha(map.AllCells.Select(c => map.terrainGrid.TerrainAt(c).defName)));
            Log.Message("[RWMT-PROBE] map roof sha=" + Sha(map.AllCells.Select(c => map.roofGrid.RoofAt(c)?.defName ?? "-")));
            // Counts, unlike the hashes, can be compared between runs that are not
            // bit-identical (map generation on this build is not reproducible run to run).
            foreach (var group in map.AllCells.GroupBy(c => map.terrainGrid.TerrainAt(c).defName).OrderBy(g => g.Key, StringComparer.Ordinal))
            {
                Log.Message($"[RWMT-PROBE] map terrain-cells {group.Key}={group.Count()}");
            }
            Log.Message($"[RWMT-PROBE] map roofed-cells={map.AllCells.Count(c => map.roofGrid.Roofed(c))}");
            List<string> things = map.listerThings.AllThings
                .Select(t => $"{t.def.defName}|{t.Position.x},{t.Position.z}|{t.Rotation.AsInt}|{t.Stuff?.defName}|{t.Faction?.def.defName}|{t.stackCount}")
                .OrderBy(s => s, StringComparer.Ordinal).ToList();
            Log.Message($"[RWMT-PROBE] map things count={things.Count} sha={Sha(things)}");
            foreach (var group in map.listerThings.AllThings.GroupBy(t => t.def.category).OrderBy(g => g.Key.ToString()))
            {
                Log.Message($"[RWMT-PROBE] map category {group.Key}={group.Count()}");
            }
            foreach (var group in map.listerThings.AllThings.GroupBy(t => t.def.defName).OrderBy(g => g.Key, StringComparer.Ordinal))
            {
                Log.Message($"[RWMT-PROBE] map thing-count {group.Key}={group.Count()}");
            }
            Log.Message("[RWMT-PROBE] map pawns " + string.Join(",", map.mapPawns.AllPawns
                .Select(p => $"{p.kindDef.defName}@{p.Position.x},{p.Position.z}").OrderBy(s => s, StringComparer.Ordinal)));
        }

        private static string Sha(IEnumerable<string> parts)
        {
            using var sha = SHA256.Create();
            byte[] bytes = Encoding.UTF8.GetBytes(string.Join("\n", parts));
            return Convert.ToHexString(sha.ComputeHash(bytes)).Substring(0, 16).ToLowerInvariant();
        }
    }
}
