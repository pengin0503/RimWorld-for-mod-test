using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
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
    // In both runs, it makes the generation seeds that .NET would randomize
    // deterministic (DeterministicGenerationSeeds), salted by the number in the
    // optional Salt.txt next to About/, so each run of a comparison can draw a
    // different, reproducible map.
    public class MapProbeMod : Mod
    {
        public const string Seed = "rwmt";
        internal static bool officialQuickTest;

        public MapProbeMod(ModContentPack content) : base(content)
        {
            var harmony = new Harmony("rwmodtest.mapprobe");
            harmony.PatchAll(typeof(MapProbeMod).Assembly);
            string salt = System.IO.Path.Combine(content.RootDir, "Salt.txt");
            DeterministicGenerationSeeds.Install(harmony,
                System.IO.File.Exists(salt) ? int.Parse(System.IO.File.ReadAllText(salt).Trim(), System.Globalization.CultureInfo.InvariantCulture) : 0);
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

    // Map generation on 1.7 is not reproducible run to run: Map.NextGenSeed (the Rand seed of every
    // BaseGen symbol, e.g. the ancient shrines) and LayoutWorker.FillAllRooms (the Rand seed of every
    // room of a layout structure) combine their inputs with System.HashCode, which .NET seeds randomly
    // in each process. In both the official and the product run, the probe replaces only that combiner
    // with the game's own Gen.HashCombineInt over the same inputs and the salt, so the two runs can be
    // compared map for map. Everything else the game does is left as it is.
    public static class DeterministicGenerationSeeds
    {
        private static readonly AccessTools.FieldRef<Map, int> GeneratedId = AccessTools.FieldRefAccess<Map, int>("generatedId");
        internal static string nextGenSeed = "missing";
        internal static int layoutRoomSeeds;
        internal static int salt;

        public static void Install(Harmony harmony, int salt)
        {
            DeterministicGenerationSeeds.salt = salt;
            MethodInfo getter = AccessTools.PropertyGetter(typeof(Map), "NextGenSeed");
            if (getter != null)
            {
                harmony.Patch(getter, prefix: new HarmonyMethod(typeof(DeterministicGenerationSeeds), nameof(NextGenSeed)));
                nextGenSeed = "replaced";
            }
            MethodInfo fillAllRooms = AccessTools.Method(typeof(LayoutWorker), "FillAllRooms");
            if (fillAllRooms != null)
            {
                harmony.Patch(fillAllRooms, transpiler: new HarmonyMethod(typeof(DeterministicGenerationSeeds), nameof(RoomSeeds)));
            }
        }

        // Map.NextGenSeed => HashCode.Combine(tile valid ? tile hash : uniqueID, generatedId++, world seed)
        public static bool NextGenSeed(Map __instance, ref int __result)
        {
            int first = __instance.TileInfo.tile.Valid ? __instance.TileInfo.tile.GetHashCode() : __instance.uniqueID;
            int id = GeneratedId(__instance)++;
            __result = Gen.HashCombineInt(Gen.HashCombineInt(Gen.HashCombineInt(first, id), Find.World.info.Seed), salt);
            return false;
        }

        public static int CombineRoomSeed(int sketchId, int room) => Gen.HashCombineInt(Gen.HashCombineInt(sketchId, room), salt);

        // LayoutWorker.FillAllRooms => new RandBlock(HashCode.Combine(structureSketch.id, room index)), three times
        public static IEnumerable<CodeInstruction> RoomSeeds(IEnumerable<CodeInstruction> instructions)
        {
            MethodInfo combine = typeof(HashCode).GetMethods(BindingFlags.Public | BindingFlags.Static)
                .Single(m => m.Name == nameof(HashCode.Combine) && m.GetGenericArguments().Length == 2)
                .MakeGenericMethod(typeof(int), typeof(int));
            MethodInfo replacement = AccessTools.Method(typeof(DeterministicGenerationSeeds), nameof(CombineRoomSeed));
            foreach (CodeInstruction instruction in instructions)
            {
                if (instruction.Calls(combine))
                {
                    layoutRoomSeeds++;
                    yield return new CodeInstruction(OpCodes.Call, replacement).WithLabels(instruction.labels).WithBlocks(instruction.blocks);
                    continue;
                }
                yield return instruction;
            }
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
            Log.Message($"[RWMT-PROBE] map seeds nextGenSeed={DeterministicGenerationSeeds.nextGenSeed} layoutRoomSeeds={DeterministicGenerationSeeds.layoutRoomSeeds} salt={DeterministicGenerationSeeds.salt}");
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
